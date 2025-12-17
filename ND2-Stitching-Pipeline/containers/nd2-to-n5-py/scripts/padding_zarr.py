import numpy as np
import tifffile

import os
import sys
import re
import argparse

import zarr
import dask
import dask.array as da
from distributed import LocalCluster, Client, Variable

from pathlib import Path

import json

import shutil

import time

def get_chunk_size_at_position(position, chunk_size, dataset_shape):
    """
    Calculate the actual chunk size at a specific position in the dataset.
    
    :param position: Tuple of integers indicating the chunk position.
    :param chunk_size: Tuple of integers indicating the regular chunk size.
    :param dataset_shape: Tuple of integers indicating the overall dataset shape.
    :return: Tuple of integers indicating the actual chunk size at the given position.
    """
    # Calculate the start and end coordinates of the chunk
    chunk_start = [pos * cs for pos, cs in zip(position, chunk_size)]
    chunk_end = [min(start + cs, ds) for start, cs, ds in zip(chunk_start, chunk_size, dataset_shape)]
    
    # Calculate the actual chunk size
    actual_chunk_size = [end - start for start, end in zip(chunk_start, chunk_end)]
    return tuple(actual_chunk_size)

def padding(data_chunk, median, amp):
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    # Set all low intensity pixels to zero
    data_chunk = data_chunk * (~masks).astype(np.uint16)

    white_noise = np.random.normal(0, 1.0, data_chunk.shape) * vv + mm
    data_chunk += (white_noise * masks).astype(np.uint16)

    return data_chunk

def read_zarr_chunk(dataset, idx, channel=None):
    """ZARRデータセットから特定のチャンクを読み込む（オプションでチャンネルを指定）"""
    # チャンクの開始位置と終了位置を計算
    chunk_size = dataset.chunks
    start = tuple(i * c for i, c in zip(idx, chunk_size))
    end = tuple(min(s + c, d) for s, c, d in zip(start, chunk_size, dataset.shape))
    
    # スライスを作成
    slices = tuple(slice(s, e) for s, e in zip(start, end))
    
    try:
        # TCZYXフォーマットの場合、特定のチャンネルだけを読み込む
        if channel is not None and len(dataset.shape) >= 5:  # TCZYXの次元がある場合
            # チャンネル次元のインデックスは1（0-indexed）
            channel_idx = int(channel)
            modified_slices = list(slices)
            modified_slices[1] = slice(channel_idx, channel_idx + 1)  # チャンネル次元のスライスを特定のチャンネルに限定
            return dataset[tuple(modified_slices)]
        else:
            # 通常通りに全チャンネルを読み込む
            return dataset[slices]
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return None

def write_zarr_chunk(dataset, idx, data, channel=None):
    """ZARRデータセットに特定のチャンクを書き込む（オプションでチャンネルを指定）"""
    # チャンクの開始位置と終了位置を計算
    chunk_size = dataset.chunks
    start = tuple(i * c for i, c in zip(idx, chunk_size))
    end = tuple(min(s + c, d) for s, c, d in zip(start, chunk_size, dataset.shape))
    
    # スライスを作成
    slices = tuple(slice(s, e) for s, e in zip(start, end))
    
    try:
        # TCZYXフォーマットの場合、特定のチャンネルだけを書き込む
        if channel is not None and len(dataset.shape) >= 5:  # TCZYXの次元がある場合
            # チャンネル次元のインデックスは1（0-indexed）
            channel_idx = int(channel)
            modified_slices = list(slices)
            modified_slices[1] = slice(channel_idx, channel_idx + 1)  # チャンネル次元のスライスを特定のチャンネルに限定
            
            # 元のデータを読み込み、特定のチャンネルだけを更新
            original_data = dataset[tuple(slices)]
            original_data[0, channel_idx - modified_slices[1].start, ...] = data[0, 0, ...]  # チャンネル次元を合わせる
            dataset[tuple(slices)] = original_data
        else:
            # 通常通りに全チャンネルを書き込む
            dataset[slices] = data
        return True
    except Exception as e:
        print(f"Error writing chunk {idx}: {e}")
        return False

def padding2(in_dataset, out_dataset, idx, median, amp, retry, wait, channel=None):
    try:
        # チャンクを読み込む
        data_chunk = read_zarr_chunk(in_dataset, idx, channel)
        create_empty = False
        if data_chunk is None:
            create_empty = True
            print(f"Chunk {idx} is missing.")
                    
        # NaNや無限大の値をチェック
        if create_empty == False:
            if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
                create_empty = True
                print(f"Chunk {idx} contains NaNs or infinite values. It will be ignored")
        
        if create_empty == True:
            # TCZYXフォーマットの場合、channel次元を考慮してゼロの配列を作成
            if channel is not None and len(in_dataset.shape) >= 5:
                # 5次元（TCZYX）のデータセットを想定
                # チャンクサイズを取得し、C次元は1に設定（特定のチャンネルのみ）
                chunk_shape = list(get_chunk_size_at_position(idx, in_dataset.chunks, in_dataset.shape))
                chunk_shape[1] = 1  # C次元を1に設定
                data_chunk = np.zeros(tuple(chunk_shape), dtype=in_dataset.dtype)
            else:
                chunk_size = get_chunk_size_at_position(idx, in_dataset.chunks, in_dataset.shape)
                data_chunk = np.zeros(chunk_size, dtype=in_dataset.dtype)
            print(f"Empty chunk {idx} is created.")
            
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return False
    
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    # Set all low intensity pixels to zero
    data_chunk = data_chunk * (~masks).astype(np.uint16)

    white_noise = np.random.normal(0, 1.0, data_chunk.shape) * vv + mm
    data_chunk += (white_noise * masks).astype(np.uint16)

    # 書き込みを試行
    for i in range(retry):
        success = write_zarr_chunk(out_dataset, idx, data_chunk, channel)
        if success and validate_chunk(out_dataset, idx, channel):
            return True
        print(f"Retry to write chunk {idx}")
        time.sleep(wait)

    return False

def compute_histogram(chunk, bins, range):
    hist, edges = np.histogram(chunk, bins=bins, range=range)
    return hist

def compute_histogram2(dataset, idx, bins, range, channel=None):
    try:
        # チャンクを読み込む（指定されたチャンネルのみ）
        data_chunk = read_zarr_chunk(dataset, idx, channel)
        if data_chunk is None:
            print(f"Chunk {idx} is missing. It will be ignored.")
            data_chunk = np.array([])
                
        # NaNや無限大の値をチェック
        if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values. It will be ignored.")
            data_chunk = np.array([])

        hist, edges = np.histogram(data_chunk, bins=bins, range=range)
        return hist
                
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return None
    
    return None

def find_median_from_histogram(histogram, range):
    # 各ビンの値を表す配列を作成
    bin_edges = np.linspace(range[0], range[1], len(histogram) + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    
    # ヒストグラムの累積和を計算
    cumulative_sum = np.cumsum(histogram)
    total_count = cumulative_sum[-1]
    
    # 累積和が合計カウントの半分に達するインデックスを見つける
    median_index = np.searchsorted(cumulative_sum, total_count / 2)
    
    # 中央値に対応するビンの中心を返す
    median_value = bin_centers[median_index]
    return int(median_value)

def validate_chunk(dataset, idx, channel=None):
    try:
        # チャンクを読み込む
        chunk = read_zarr_chunk(dataset, idx, channel)
        if chunk is None:
            print(f"Chunk {idx} is missing.")
            return False
                
        # NaNや無限大の値をチェック
        if np.isnan(chunk).any() or np.isinf(chunk).any():
            print(f"Chunk {idx} contains NaNs or infinite values.")
            return False
                
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return False
    
    return True

def copy_attributes(source_path, dest_path):
    """ZARRグループまたはデータセットから属性をコピー"""
    if os.path.exists(source_path + '/.zattrs'):
        # 属性ファイルをコピー
        shutil.copy2(source_path + '/.zattrs', dest_path + '/.zattrs')
    return True

def padding_in_place(dataset, idx, median, amp, retry, wait, channel=None):
    """
    既存のデータセットを直接上書きするパディング処理
    """
    try:
        # チャンクを読み込む（指定されたチャンネルのみ）
        data_chunk = read_zarr_chunk(dataset, idx, channel)
        create_empty = False
        if data_chunk is None:
            create_empty = True
            print(f"Chunk {idx} is missing.")
                    
        # NaNや無限大の値をチェック
        if create_empty == False:
            if np.isnan(data_chunk).any() or np.isinf(data_chunk).any():
                create_empty = True
                print(f"Chunk {idx} contains NaNs or infinite values. It will be ignored")
        
        if create_empty == True:
            # TCZYXフォーマットの場合、channel次元を考慮してゼロの配列を作成
            if channel is not None and len(dataset.shape) >= 5:
                # 5次元（TCZYX）のデータセットを想定
                # チャンクサイズを取得し、C次元は1に設定（特定のチャンネルのみ）
                chunk_shape = list(get_chunk_size_at_position(idx, dataset.chunks, dataset.shape))
                chunk_shape[1] = 1  # C次元を1に設定
                data_chunk = np.zeros(tuple(chunk_shape), dtype=dataset.dtype)
            else:
                chunk_size = get_chunk_size_at_position(idx, dataset.chunks, dataset.shape)
                data_chunk = np.zeros(chunk_size, dtype=dataset.dtype)
            print(f"Empty chunk {idx} is created.")
            
    except Exception as e:
        print(f"Error reading chunk {idx}: {e}")
        return False
    
    # オリジナルデータを保存（上書き失敗時の復旧用）
    original_data = data_chunk.copy()
    
    mm = median

    # Calculate vv
    vv = int(mm // amp)  # Use integer division

    # Generate masks for low intensity pixels
    masks = (data_chunk < mm - vv)

    # Set all low intensity pixels to zero
    data_chunk = data_chunk * (~masks).astype(np.uint16)

    white_noise = np.random.normal(0, 1.0, data_chunk.shape) * vv + mm
    data_chunk += (white_noise * masks).astype(np.uint16)

    # 書き込みを試行
    for i in range(retry):
        success = write_zarr_chunk(dataset, idx, data_chunk, channel)
        if success and validate_chunk(dataset, idx, channel):
            return True
        print(f"Retry to write chunk {idx}")
        time.sleep(wait)
        
        # 最終試行で失敗した場合、元のデータを復元
        if i == retry - 1:
            try:
                write_zarr_chunk(dataset, idx, original_data, channel)
                print(f"Restored original data for chunk {idx}")
            except Exception as e:
                print(f"Error restoring original data for chunk {idx}: {e}")

    return False

def print_zarr_structure(group, prefix="", verbose=False):
    """
    Zarrグループの構造を再帰的に表示する関数
    
    Args:
        group: Zarrグループオブジェクト
        prefix: 表示時の階層を示すプレフィックス
        verbose: 詳細情報（属性やデータセットの形状など）を表示するかどうか
    """
    # 子グループを処理
    for key in group.group_keys():
        print(f"{prefix}└── {key}/ (Group)")
        if verbose and '.zattrs' in os.listdir(os.path.join(group.store.path, group.path, key)):
            try:
                attrs = group[key].attrs.asdict()
                if attrs:
                    print(f"{prefix}    ├── Attributes: {attrs}")
            except Exception as e:
                print(f"{prefix}    ├── Error reading attributes: {e}")
        
        # 再帰的に子グループの内容を表示
        print_zarr_structure(group[key], prefix + "    ", verbose)
    
    # データセットを処理
    for key in group.array_keys():
        array = group[key]
        shape_str = f"shape={array.shape}, chunks={array.chunks}, dtype={array.dtype}"
        print(f"{prefix}└── {key} (Array: {shape_str})")
        
        if verbose:
            try:
                attrs = array.attrs.asdict()
                if attrs:
                    print(f"{prefix}    └── Attributes: {attrs}")
            except Exception as e:
                print(f"{prefix}    └── Error reading attributes: {e}")

def get_all_zarr_paths(root_path, include_arrays=True):
    """
    指定されたZarrファイル内のすべてのグループとデータセットのパスを再帰的に取得する
    
    Args:
        root_path: Zarrファイルのルートパス
        include_arrays: データセット（配列）も含めるかどうか
        
    Returns:
        すべてのグループ（とオプションでデータセット）のパスのリスト
    """
    result = []
    root = zarr.open(root_path, mode='r')
    
    def _visit_group(group, current_path=""):
        # 現在のグループのパスを追加
        if current_path:
            result.append(current_path)
        
        # 子グループを再帰的に処理
        for key in group.group_keys():
            child_path = f"{current_path}/{key}" if current_path else key
            _visit_group(group[key], child_path)
        
        # データセットを処理（オプション）
        if include_arrays:
            for key in group.array_keys():
                array_path = f"{current_path}/{key}" if current_path else key
                result.append(array_path)
    
    _visit_group(root)
    return result

def main():
    argv = sys.argv
    argv = argv[1:]

    usage_text = ("Usage:" + "  padding_zarr.py" + " [options]")
    parser = argparse.ArgumentParser(description=usage_text)
    parser.add_argument("-i", "--input", dest="input", type=str, default=None, help="input file path (.zarr)")
    parser.add_argument("-t", "--thread", dest="thread", type=int, default=0, help="number of threads")
    parser.add_argument("-c", "--ch", dest="ch", type=str, default=0, help="channel")
    parser.add_argument("-s", "--scale", dest="scale", type=str, default=0, help="scale")
    parser.add_argument("--verbose", dest="verbose", default=False, action="store_true", help="enable verbose logging")
    parser.add_argument("--inplace", dest="inplace", default=False, action="store_true", help="directly update existing datasets without creating temporary ones")

    if not argv:
        parser.print_help()
        exit()

    args = parser.parse_args(argv)

    input_path = args.input
    ch = args.ch
    scales = args.scale.split(",")
    threadnum = args.thread
    inplace = args.inplace
    
    # チャンネルを数値に変換
    try:
        channel = int(ch)
    except ValueError:
        print(f"Invalid channel value: {ch}. Using default channel 0.")
        channel = 0

    # ベースパスを設定
    base_path = input_path
    
    # 処理対象のグループパスを取得
    group_paths = []
    for scale in scales:
        group_path = '' + scale
        group_paths.append(group_path)

    # ZARRファイルを開く
    zarr_root = zarr.open(base_path, mode='a')

    bins = 65534
    range = (1, 65535)

    # Daskクラスターをセットアップ
    cluster = LocalCluster(n_workers=threadnum, threads_per_worker=1)
    client = Client(cluster)

    all_group_paths = get_all_zarr_paths(base_path)
    for path in sorted(all_group_paths):
        print(path)
    
    # 各グループを処理
    for g in group_paths:
        full_group_path = os.path.join(base_path, g)
        
        # 現在のグループにアクセス (ネストされたグループをサポート)
        try:
            group_parts = g.split('/')
            current_group = zarr_root
            for part in group_parts:
                if part:  # 空の部分をスキップ
                    current_group = current_group[part]
        except KeyError:
            print(f"Group {g} does not exist. Skipping.")
            continue
        
        # データセットの形状とチャンクサイズを取得
        shape = current_group.shape
        chunks = current_group.chunks
        num_chunks = tuple(int(np.ceil(s / c)) for s, c in zip(shape, chunks))
        
        # TCZYXフォーマットかどうかを確認
        is_tczyx = len(shape) >= 5
        
        # データセットの形状を表示
        print(f"Dataset shape: {shape}, chunks: {chunks}, format: {'TCZYX' if is_tczyx else 'Unknown'}")
        
        if is_tczyx:
            print(f"Processing channel {channel} only")
        
        # ヒストグラム計算のためのfuturesを作成
        futures = []
        for idx in np.ndindex(*num_chunks):
            future = dask.delayed(compute_histogram2)(
                dataset=current_group, 
                idx=idx, 
                bins=bins, 
                range=range,
                channel=channel if is_tczyx else None
            )
            futures.append(future)
        
        # 並列計算を実行
        histograms = dask.compute(futures)[0]
        
        # 全体のヒストグラムと中央値を計算
        valid_histograms = [h for h in histograms if h is not None]
        if not valid_histograms:
            print(f"No valid histograms found for {g}. Skipping.")
            continue
            
        overall_histogram = np.sum(valid_histograms, axis=0)
        median_value = find_median_from_histogram(overall_histogram, range)
        
        print(f"Processing group {g} with median value: {median_value}")
        
        if inplace:
            # 直接上書きモード
            futures = []
            for idx in np.ndindex(*num_chunks):
                future = dask.delayed(padding_in_place)(
                    dataset=current_group,
                    idx=idx,
                    median=median_value,
                    amp=10,
                    retry=10,
                    wait=5,
                    channel=channel if is_tczyx else None
                )
                futures.append(future)
            
            # 並列処理実行
            padding_results = dask.compute(futures)[0]
            print(f"In-place padding completed for {g}")
            
        else:
            # 一時データセット作成モード（元のコード）
            # 新しいデータセットパスを設定
            new_dataset_path = 'tmp_' + g
            new_dataset_full_path = os.path.join(base_path, new_dataset_path)
            
            # tmp_から始まるディレクトリ構造を作成
            os.makedirs(os.path.dirname(new_dataset_full_path), exist_ok=True)
            
            # 新しいデータセットを作成
            # ZARRのデータセットをネストして作成
            tmp_parts = new_dataset_path.split('/')
            tmp_group = zarr_root
            for i, part in enumerate(tmp_parts[:-1]):
                if part and part not in tmp_group:  # 空の部分をスキップ
                    tmp_group.create_group(part)
                if part:  # 空の部分をスキップ
                    tmp_group = tmp_group[part]
            
            # 最後の部分がデータセット名
            final_name = tmp_parts[-1]
            new_dataset = tmp_group.create_dataset(final_name, 
                                                shape=shape, 
                                                chunks=chunks, 
                                                dtype=current_group.dtype)
            
            # 属性をコピー（存在する場合）
            if os.path.exists(os.path.join(full_group_path, '.zattrs')):
                shutil.copy2(
                    os.path.join(full_group_path, '.zattrs'),
                    os.path.join(new_dataset_full_path, '.zattrs')
                )
            
            # パディング処理のfuturesを作成
            futures = []
            for idx in np.ndindex(*num_chunks):
                future = dask.delayed(padding2)(
                    in_dataset=current_group, 
                    out_dataset=new_dataset, 
                    idx=idx, 
                    median=median_value, 
                    amp=10, 
                    retry=10, 
                    wait=5,
                    channel=channel if is_tczyx else None
                )
                futures.append(future)
            
            # 並列処理実行
            padding_results = dask.compute(futures)[0]
            
            # 古いデータセットを削除し、新しいデータセットを移動
            try:
                # ZARRでは、ディレクトリ構造を移動/上書きする
                if os.path.exists(full_group_path):
                    shutil.rmtree(full_group_path)
                shutil.move(new_dataset_full_path, full_group_path)
                
                # tmpディレクトリを全て削除（断片を残さないようにする）
                tmp_setup_path = os.path.join(base_path, 'tmp_setup'+str(ch))
                if os.path.exists(tmp_setup_path):
                    shutil.rmtree(tmp_setup_path)
            except shutil.Error as e:
                print("Error moving the directory:", e)

    # クライアントとクラスタを閉じる
    client.close()
    cluster.close()

if __name__ == '__main__':
    main()