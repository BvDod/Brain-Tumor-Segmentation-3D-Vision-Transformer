import monai
from monai.transforms import RandFlipd, NormalizeIntensityd, NormalizeIntensityd, RandScaleIntensityd, RandShiftIntensityd, RandSpatialCropd, SpatialCropd
from torchvision import transforms

def get_transforms_3d(patch_size):
    """ Transforms for 3D data, used in training """

    transforms = monai.transforms.Compose([
        RandSpatialCropd(keys=["image", "label"], roi_size=(192, 192, 128), random_size=False),
        RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=0),
        RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=1),
        RandFlipd(keys=["image", "label"], prob=0.5, spatial_axis=2),
        monai.transforms.DivisiblePadd(keys=["image", "label"], k=patch_size),
    ])
    return transforms


def get_transforms_3d_val(patch_size):
    """ Transforms for 3D data, used in validation """
    
    transforms = monai.transforms.Compose([
        SpatialCropd(keys=["image", "label"], roi_center=(120, 120, 75), roi_size=(192, 192, 128)),
        monai.transforms.DivisiblePadd(keys=["image", "label"], k=patch_size),
    ])
    return transforms