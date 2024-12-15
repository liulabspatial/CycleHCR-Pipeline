import zarr
import numpy as np
import tifffile

from bigstream.level_set import foreground_segmentation
from scipy.ndimage import zoom, binary_closing, binary_dilation
from scipy.ndimage import binary_fill_holes
from skimage.filters import threshold_triangle, gaussian
from skimage import io, transform, measure, morphology
from scipy.ndimage import maximum_filter, minimum_filter, generate_binary_structure

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

fixdir = '/nrs/liu/Takashi/hippo_ETS12_rep/b2/t1/'
fix_zarr = zarr.open(store=zarr.N5FSStore(fixdir), mode='r')
fix = fix_zarr['c3/s2']
spacing = np.multiply(fix.attrs.asdict()['pixelResolution'],fix.attrs.asdict()['downsamplingFactors'])[::-1]
print('fix:',fix.shape)
print('spacing:',spacing)

fix_np = fix[:]
max_intensity = np.max(fix_np)
bg_val = threshold_triangle(fix_np, nbins=max_intensity)
fix_np[fix_np < bg_val] = 0

print('background: ', bg_val)

scale_factors = (0.2, 0.1, 0.1) 
new_shape = tuple(int(dim * scale) for dim, scale in zip(fix_np.shape, scale_factors))
scaled_image = transform.resize(fix_np, new_shape, mode='edge', anti_aliasing=True)
print('scaled')

radius = 15
# Create a spherical structuring element
structuring_element = generate_binary_structure(3, 1)  # 3D connectivity
structuring_element = maximum_filter(structuring_element, size=radius)

dilated_image = maximum_filter(scaled_image, footprint=structuring_element)
print('dilated')
closed_image = minimum_filter(dilated_image, footprint=structuring_element)
print('eroded')
binary_image = np.where(closed_image > 0, 1, 0).astype(np.uint8)
print('binarized')

fix_mask_fill = np.zeros_like(binary_image)
for z in range(binary_image.shape[0]):
    fix_mask_fill[z,:,:] = binary_fill_holes(binary_image[z,:,:])
print('mask:',fix_mask_fill.shape)
print('mask,dtype:',fix_mask_fill.dtype)

labeled_image, num_features = measure.label(fix_mask_fill, background=0, return_num=True)
properties = measure.regionprops(labeled_image)
largest_component = max(properties, key=lambda x: x.area)
largest_segment = np.zeros_like(binary_image, dtype=binary_image.dtype)
largest_segment[labeled_image == largest_component.label] = 1

binary_image2 = np.where(largest_segment > 0, 255, 0).astype(np.uint8)
print('binarized')

# Apply Gaussian blur
sigma = 3  # Adjust this value for more or less blurring
blurred_image = gaussian(binary_image2, sigma=sigma, mode='nearest', preserve_range=True)
#binary_image3 = (blurred_image > 127).astype(np.uint8)
print('smoothed')

scaled_image = transform.resize(blurred_image, fix_np.shape, mode='edge', anti_aliasing=True)
print('scaled')

binary_image4 = (scaled_image > 127).astype(np.uint8)
print('binarized')

fix_mask_fill = binary_image4

mask_path = './test.tiff'
tifffile.imwrite(mask_path,fix_mask_fill,imagej=True,metadata={'axes':'ZYX'})