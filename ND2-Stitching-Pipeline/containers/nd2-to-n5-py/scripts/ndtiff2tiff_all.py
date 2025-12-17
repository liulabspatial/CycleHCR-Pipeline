import gc
import os
import pandas as pd
import numpy as np
import ndstorage as nds
import tifffile
import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import glob
import dask
from dask.distributed import Client, LocalCluster
from dask import delayed

class NDTiffProcessor:
    def __init__(self, position_dir, position_id, timepoint_id):
        self.position_dir = position_dir
        self.position_id = position_id
        self.timepoint_id = timepoint_id
        self.xy_positions = None
        self.z_positions = {}
        self.layer_ids = []
        self.tile_labels = None
        self.voxel_size = None  # (dx, dy, dz)
        self.load_metadata()
    
    def get_xy_pixel_size(self, folder_path):
        tiff_files = []
        for ext in ['.tif', '.tiff', '.TIF', '.TIFF']:
            tiff_files.extend(glob.glob(os.path.join(folder_path, f'*{ext}')))
            
        if not tiff_files:
            print(f"Warning: No TIFF files found in {folder_path}")
            return None, None
            
        first_tiff = tiff_files[0]
        try:
            with tifffile.TiffFile(first_tiff) as tif:
                tags = tif.pages[0].tags
                if 'XResolution' in tags and 'YResolution' in tags:
                    x_res = tags['XResolution'].value
                    y_res = tags['YResolution'].value
                    
                    if isinstance(x_res, tuple):
                        dx = (float(x_res[1]) / float(x_res[0])) * 10000
                    else:
                        dx = (float(x_res.denominator) / float(x_res.numerator)) * 10000
                        
                    if isinstance(y_res, tuple):
                        dy = (float(y_res[1]) / float(y_res[0])) * 10000
                    else:
                        dy = (float(y_res.denominator) / float(y_res.numerator)) * 10000
                        
                    print(f"Got pixel size from {os.path.basename(first_tiff)}: dx={dx}µm, dy={dy}µm")
                    return dx, dy
                else:
                    print(f"Warning: XResolution or YResolution tags not found in {first_tiff}")
        except Exception as e:
            print(f"Error reading TIFF file {first_tiff}: {str(e)}")
            print(f"Tags found in file: {list(tags.keys()) if 'tags' in locals() else 'No tags accessed'}")
            
        return None, None
        
    def get_z_step(self, layer_id):
        if layer_id in self.z_positions:
            z_positions = self.z_positions[layer_id]
            if len(z_positions) >= 2:
                return abs(z_positions[1] - z_positions[0])
        return None

    def load_metadata(self):
        # Load XY positions from position directory
        xy_path = os.path.join(self.position_dir, 'layer_xy_position_plan.csv')
        if not os.path.exists(xy_path):
            raise FileNotFoundError(f"XY position file not found: {xy_path}")
        
        self.xy_positions = pd.read_csv(xy_path)
        
        # Flip X coordinates (multiply by -1) and swap X and Y coordinates
        self.xy_positions['X_original'] = self.xy_positions['X'].copy()
        self.xy_positions['X'] = self.xy_positions['Y'].copy()
        self.xy_positions['Y'] = -1 * self.xy_positions['X_original']
        # Drop the temporary column
        self.xy_positions = self.xy_positions.drop('X_original', axis=1)
        
        print(f"Position {self.position_id}, Timepoint {self.timepoint_id} - XY coordinates after adjustment:")
        print(self.xy_positions[['Label', 'X', 'Y']].head())

        self.tile_labels = self.xy_positions['Label'].tolist()
        
        # Look for layer directories in timepoint directory
        timepoint_dir = os.path.join(self.position_dir, f't{self.timepoint_id}')
        if not os.path.exists(timepoint_dir):
            raise FileNotFoundError(f"Timepoint directory not found: {timepoint_dir}")
        
        for layer_dir in os.listdir(timepoint_dir):
            if os.path.isdir(os.path.join(timepoint_dir, layer_dir)) and layer_dir.startswith('Layer'):
                try:
                    layer_id = int(layer_dir[6:])  # Extract layer number from Layer_{layer_id}
                except ValueError:
                    print(f"Warning: Invalid layer directory name: {layer_dir}")
                    continue
                self.layer_ids.append(layer_id)
                
                # Load Z positions from position directory
                z_path = os.path.join(self.position_dir, f'layer_{layer_id}_z_plan.csv')
                if os.path.exists(z_path):
                    z_positions = pd.read_csv(z_path)['Z Position'].values
                    z_positions = -1 * z_positions  # Z位置に-1をかける
                    z_positions = z_positions[::-1]  # 配列を逆順にする
                    self.z_positions[layer_id] = z_positions
                else:
                    print(f"Warning: Z position file not found: {z_path}")
        
        self.layer_ids.sort()
        
        if not self.layer_ids:
            raise ValueError(f"No layer directories found in {timepoint_dir}")
        
        # Get voxel size from first layer
        first_layer_dir = os.path.join(timepoint_dir, f'Layer_{self.layer_ids[0]}')
        first_tile_dir = os.path.join(first_layer_dir, f"{self.tile_labels[0]}_1")
        
        dx, dy = self.get_xy_pixel_size(first_tile_dir)
        if dx is None or dy is None:
            print("Warning: Could not get pixel size from TIFF files. Using default values.")
            dx = dy = 1.0

        dz = self.get_z_step(self.layer_ids[0])
        if dz is None:
            print("Warning: Could not calculate Z step size. Using default value.")
            dz = 1.0
            
        self.voxel_size = (dx, dy, dz)
        print(f"Position {self.position_id}, Timepoint {self.timepoint_id} - Voxel size: dx={dx}, dy={dy}, dz={dz}")
    
    def extract_tiff_stack(self, channel_index, label, layer_id, output_path, skip_tiff_save=False):
        # New path structure: position_dir/t{timepoint_id}/Layer_{layer_id}/{label}_1
        layer_dir = f'Layer_{layer_id}'
        timepoint_dir = f't{self.timepoint_id}'
        tile_dir = f"{label}_1"
        tile_path = os.path.join(self.position_dir, timepoint_dir, layer_dir, tile_dir)
        
        if not os.path.exists(tile_path):
            print(f"Warning: Tile directory not found: {tile_path}")
            return None
        
        try:
            ndtiff_data = nds.Dataset(tile_path)
            channels = sorted(list(ndtiff_data.axes['channel']), reverse=True)  # Reversed the channel order
            channel = channels[channel_index]
            
            slices = []
            # Z軸のスライスを取得し、逆順に並び替え
            z_values = sorted(list(ndtiff_data.axes['z']), reverse=True)  # Z値を逆順にソート
            for z in z_values:
                slice_data = ndtiff_data.read_image(channel=channel, z=z)
                slices.append(slice_data)
            
            stack = np.stack(slices, axis=0)
            stack = np.expand_dims(stack, axis=0)
            stack = np.expand_dims(stack, axis=2)
            
            stack_shape = stack.shape
            
            # Always create the output directory
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if not skip_tiff_save:
                tifffile.imwrite(
                    output_path,
                    stack,
                    imagej=True,
                    metadata={'axes': 'TZCYX'},
                    compression="ZLIB",
                    compressionargs={"level": 6}
                )
                print(f"Saved: {output_path}, Shape: {stack_shape}")
            else:
                # Create an empty file for testing
                with open(output_path, 'w') as f:
                    pass  # Create empty file
                print(f"Created empty file: {output_path}, Shape: {stack_shape}")
            
            del stack, slices
            gc.collect()

            return stack_shape
        except Exception as e:
            print(f"Error processing {tile_path}: {str(e)}")
            return None
    
    def create_bdv_metadata(self, output_dir, stack_shapes, first_ndtiff_data):
        """
        Create BigDataViewer metadata XML for a single position/timepoint combination.
        """
        root = ET.Element('SpimData')
        root.set('version', '0.2')
        
        # BasePath
        bp = ET.SubElement(root, 'BasePath')
        bp.set('type', 'relative')
        bp.text = '.'
        
        # SequenceDescription
        seq_desc = ET.SubElement(root, 'SequenceDescription')
        
        # ImageLoader
        img_loader = ET.SubElement(seq_desc, 'ImageLoader')
        img_loader.set('format', 'spimreconstruction.filemap2')

        # ZGrouped要素を追加
        zgrouped = ET.SubElement(img_loader, 'ZGrouped')
        zgrouped.text = 'false'
        
        # FileMappings
        files = ET.SubElement(img_loader, 'files')
        setup_id = 0
        
        for layer_id in self.layer_ids:
            for ch_idx, ch in enumerate(sorted(list(first_ndtiff_data.axes['channel']))):
                for label in self.tile_labels:
                    file_mapping = ET.SubElement(files, 'FileMapping')
                    file_mapping.set('view_setup', str(setup_id))
                    file_mapping.set('timepoint', "0")
                    file_mapping.set('series', "0")
                    file_mapping.set('channel', "0")
                    
                    file_elem = ET.SubElement(file_mapping, 'file')
                    file_elem.set('type', 'relative')
                    file_elem.text = f'layer{layer_id}_{label}_ch{ch_idx}.tif'
                    
                    setup_id += 1
        
        # ViewSetups
        view_setups = ET.SubElement(seq_desc, 'ViewSetups')
        setup_id = 0
        
        for layer_id in self.layer_ids:
            for ch_idx, ch in enumerate(sorted(list(first_ndtiff_data.axes['channel']))):
                for label in self.tile_labels:
                    view_setup = ET.SubElement(view_setups, 'ViewSetup')
                    
                    id_elem = ET.SubElement(view_setup, 'id')
                    id_elem.text = str(setup_id)
                    
                    name_elem = ET.SubElement(view_setup, 'name')
                    name_elem.text = str(setup_id)
                    
                    # Get specific stack shape for this combination
                    shape_key = (layer_id, label, ch_idx)
                    if shape_key in stack_shapes and stack_shapes[shape_key] is not None:
                        current_shape = stack_shapes[shape_key]
                        size_elem = ET.SubElement(view_setup, 'size')
                        size_elem.text = f'{current_shape[4]} {current_shape[3]} {current_shape[1]}'
                    else:
                        print(f"Warning: No shape information for layer{layer_id}_{label}_ch{ch_idx}")
                        # Use a default size or skip this element
                        size_elem = ET.SubElement(view_setup, 'size')
                        size_elem.text = '0 0 0'
                    
                    vox_size = ET.SubElement(view_setup, 'voxelSize')
                    unit_elem = ET.SubElement(vox_size, 'unit')
                    unit_elem.text = 'µm'
                    size_elem = ET.SubElement(vox_size, 'size')
                    size_elem.text = f'{self.voxel_size[0]} {self.voxel_size[1]} {self.voxel_size[2]}'

                    tile_index = self.tile_labels.index(label) + self.layer_ids.index(layer_id) * len(self.tile_labels)
                    
                    attributes = ET.SubElement(view_setup, 'attributes')
                    for attr_name, attr_value in [
                        ('illumination', '0'),
                        ('channel', str(ch_idx)),
                        ('tile', str(tile_index)),
                        ('angle', '0')
                    ]:
                        attr_elem = ET.SubElement(attributes, attr_name)
                        attr_elem.text = attr_value
                    
                    setup_id += 1
        
        # Attributes
        # Generate tile locations for all layers
        tile_data = []
        tile_id = 0
        for layer_id in self.layer_ids:
            for label, row in self.xy_positions.iterrows():
                tile_data.append({
                    'id': tile_id,
                    'name': f"{tile_id}",
                    'location': f"{row['X']} {row['Y']} {self.z_positions[layer_id][0]}"
                })
                tile_id += 1

        for attr_name, attr_data in [
            ('illumination', [{'id': 0, 'name': '0'}]),
            ('channel', [{'id': i, 'name': ch} for i, ch in 
                        enumerate(sorted(list(first_ndtiff_data.axes['channel'])))]),
            ('tile', tile_data),
            ('angle', [{'id': 0, 'name': '0'}])
        ]:
            attrs = ET.SubElement(view_setups, 'Attributes')
            attrs.set('name', attr_name)
            for item in attr_data:
                elem = ET.SubElement(attrs, attr_name.capitalize())
                for k, v in item.items():
                    sub_elem = ET.SubElement(elem, k)
                    sub_elem.text = str(v)
        
        # Timepoints (single timepoint for each project)
        timepoints = ET.SubElement(seq_desc, 'Timepoints')
        timepoints.set('type', 'range')
        first = ET.SubElement(timepoints, 'first')
        first.text = "0"
        last = ET.SubElement(timepoints, 'last')
        last.text = "0"
        
        # ViewRegistrations
        view_regs = ET.SubElement(root, 'ViewRegistrations')
        setup_id = 0
        
        for layer_id in self.layer_ids:
            for ch_idx in range(len(first_ndtiff_data.axes['channel'])):
                for label, row in self.xy_positions.iterrows():
                    view_reg = ET.SubElement(view_regs, 'ViewRegistration')
                    view_reg.set('timepoint', str(0))
                    view_reg.set('setup', str(setup_id))
                    
                    z_scale = 1.0 / self.voxel_size[0]
                    
                    # Translation transform with scaled coordinates
                    trans = ET.SubElement(view_reg, 'ViewTransform')
                    trans.set('type', 'affine')
                    trans_name = ET.SubElement(trans, 'Name')
                    trans_name.text = 'Translation'
                    trans_matrix = ET.SubElement(trans, 'affine')
                    
                    # Scale the translation components
                    scaled_x = float(row['X']) * z_scale
                    scaled_y = float(row['Y']) * z_scale
                    scaled_z = float(self.z_positions[layer_id][0]) * z_scale
                    
                    trans_matrix.text = (f"1.0 0.0 0.0 {scaled_x} "
                                        f"0.0 1.0 0.0 {scaled_y} "
                                        f"0.0 0.0 1.0 {scaled_z}")
                    
                    # Calibration transform
                    calib = ET.SubElement(view_reg, 'ViewTransform')
                    calib.set('type', 'affine')
                    calib_name = ET.SubElement(calib, 'Name')
                    calib_name.text = 'calibration'
                    calib_matrix = ET.SubElement(calib, 'affine')
                    calib_matrix.text = f"1.0 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 0.0 {self.voxel_size[2]/self.voxel_size[0]} 0.0"
                    
                    setup_id += 1
        
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent='  ')
        # <?xml version="1.0" ?>の行を削除
        xml_str = '\n'.join(xml_str.split('\n')[1:])
        xml_path = os.path.join(output_dir, f'bdv_metadata_p{self.position_id}_t{self.timepoint_id}.xml')
        with open(xml_path, 'w') as f:
            f.write(xml_str)
        
        return xml_path
    
    def process_single_combination(self, ch_idx, layer_id, label, output_path, skip_tiff_save=False):
        print(f"Processing: p{self.position_id}_t{self.timepoint_id}_layer{layer_id}_{label}_ch{ch_idx}")
        return self.extract_tiff_stack(ch_idx, label, layer_id, output_path, skip_tiff_save)

    def process_position_timepoint(self, output_dir, worker_num, skip_tiff_save=False):
        # Get first layer and tile for channel information
        first_layer = f'Layer_{self.layer_ids[0]}'
        first_label = self.tile_labels[0]
        timepoint_dir = f't{self.timepoint_id}'
        first_path = os.path.join(self.position_dir, timepoint_dir, first_layer, f"{first_label}_1")
        
        if not os.path.exists(first_path):
            print(f"Error: First tile path not found: {first_path}")
            return None
        
        ndtiff_data = nds.Dataset(first_path)
        channels = sorted(list(ndtiff_data.axes['channel']))

        # Create output directory structure: output_dir/p{position_id}/t{timepoint_id}/
        position_output_dir = os.path.join(output_dir, f'p{self.position_id}')
        pos_time_output_dir = os.path.join(position_output_dir, f't{self.timepoint_id}')
        # Always create the directory since we'll create files (even if empty)
        os.makedirs(pos_time_output_dir, exist_ok=True)

        # Check if this is a single tile case (1 layer, 1 tile)
        if len(self.layer_ids) == 1 and len(self.tile_labels) == 1:
            single_tile_file = os.path.join(pos_time_output_dir, 'SingleTile')
            with open(single_tile_file, 'w') as f:
                pass  # Create empty file
            print(f"Single tile detected - created marker file: {single_tile_file}")

        cluster = LocalCluster(
            n_workers=worker_num,
            threads_per_worker=1,
            memory_limit='8GB'
        )
        client = Client(cluster)
        print(f"Processing position {self.position_id}, timepoint {self.timepoint_id}")
        if skip_tiff_save:
            print("TIFF saving is SKIPPED - creating empty files and metadata only")
        print(f"Dask dashboard available at: {client.dashboard_link}")

        try:
            delayed_tasks = []
            stack_shapes = {}

            for ch_idx, _ in enumerate(channels):
                for layer_id in self.layer_ids:
                    for label in self.tile_labels:
                        output_path = os.path.join(
                            pos_time_output_dir,
                            f'layer{layer_id}_{label}_ch{ch_idx}.tif'
                        )
                        
                        task = delayed(self.process_single_combination)(
                            ch_idx, layer_id, label, output_path, skip_tiff_save
                        )
                        delayed_tasks.append((task, (layer_id, label, ch_idx)))

            print(f"Scheduling {len(delayed_tasks)} tasks for parallel processing...")
            
            # Compute all tasks and collect results
            results = dask.compute([task for task, _ in delayed_tasks])[0]
            
            # Map results to their corresponding keys
            for result, (task, key) in zip(results, delayed_tasks):
                if result is not None:
                    stack_shapes[key] = result

            xml_path = None
            if stack_shapes:
                print(f"Generating BigDataViewer metadata for position {self.position_id}, timepoint {self.timepoint_id}...")
                xml_path = self.create_bdv_metadata(pos_time_output_dir, stack_shapes, ndtiff_data)
                print("BigDataViewer metadata generated successfully.")
            else:
                print(f"Warning: No valid stacks were generated for position {self.position_id}, timepoint {self.timepoint_id}")

            return xml_path

        finally:
            client.close()
            cluster.close()


def discover_positions_and_timepoints(root_dir):
    """
    Discover all position and timepoint combinations in the root directory.
    Returns list of tuples: (position_dir, position_id, timepoint_id)
    """
    combinations = []
    
    for item in os.listdir(root_dir):
        if item.startswith('p') and os.path.isdir(os.path.join(root_dir, item)):
            try:
                position_id = int(item[1:])  # Extract position ID from p{positionID}
                position_dir = os.path.join(root_dir, item)
                
                # Look for timepoint directories in this position
                for timepoint_item in os.listdir(position_dir):
                    if timepoint_item.startswith('t') and os.path.isdir(os.path.join(position_dir, timepoint_item)):
                        try:
                            timepoint_id = int(timepoint_item[1:])  # Extract timepoint ID from t{timepointID}
                            combinations.append((position_dir, position_id, timepoint_id))
                        except ValueError:
                            print(f"Warning: Invalid timepoint directory name: {timepoint_item}")
                            continue
            except ValueError:
                print(f"Warning: Invalid position directory name: {item}")
                continue
    
    return sorted(combinations)


def main(argv=None):
    parser = argparse.ArgumentParser(description='NDTiff Stack Extractor')
    parser.add_argument('-i', '--input', dest='input', type=str, required=True,
                        help='input directory')
    parser.add_argument('-o', '--output', dest='output', type=str, required=True,
                        help='output directory')
    parser.add_argument("-c", "--csv", dest="output_csv_path", type=str, default=None, 
                        help="output csv file path (.csv)")
    parser.add_argument('--memory-limit', dest='memory_limit', type=str, default='4GB',
                        help='memory limit per worker (default: 4GB)')
    parser.add_argument('--n-workers', dest='n_workers', type=int, 
                        default=os.cpu_count(),
                        help='number of worker processes (default: number of CPU cores)')
    parser.add_argument('--skip-tiff', dest='skip_tiff_save', action='store_true',
                        help='skip TIFF file saving for testing (generate metadata only)')
    
    if not argv:
        parser.print_help()
        return
        
    args = parser.parse_args(argv)
    
    os.makedirs(args.output, exist_ok=True)

    print(f"input: {args.input}")
    print(f"output: {args.output}")
    print(f"output_csv_path: {args.output_csv_path}")
    print(f"skip_tiff_save: {args.skip_tiff_save}")
    
    # Discover all position/timepoint combinations
    combinations = discover_positions_and_timepoints(args.input)
    
    if not combinations:
        print("Error: No position/timepoint combinations found in input directory")
        return
    
    print(f"Found {len(combinations)} position/timepoint combinations:")
    for position_dir, position_id, timepoint_id in combinations:
        print(f"  Position {position_id}, Timepoint {timepoint_id}")
    
    xml_files = []
    
    # Process each combination separately
    for position_dir, position_id, timepoint_id in combinations:
        try:
            print(f"\n{'='*60}")
            print(f"Processing Position {position_id}, Timepoint {timepoint_id}")
            print(f"{'='*60}")
            
            processor = NDTiffProcessor(position_dir, position_id, timepoint_id)
            xml_path = processor.process_position_timepoint(args.output, args.n_workers, args.skip_tiff_save)
            
            if xml_path:
                xml_files.append(xml_path)
                
        except Exception as e:
            print(f"Error processing position {position_id}, timepoint {timepoint_id}: {str(e)}")
            continue
    
    # Write CSV file with all generated XML files
    if args.output_csv_path and xml_files:
        with open(args.output_csv_path, 'w') as csvfile:
            for fname in xml_files:
                csvfile.write(fname + "\n")
        print(f"\nGenerated {len(xml_files)} BigDataViewer projects")
        print(f"XML file list saved to: {args.output_csv_path}")


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])