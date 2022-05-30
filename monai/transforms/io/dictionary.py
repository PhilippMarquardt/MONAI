# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
A collection of dictionary-based wrappers around the "vanilla" transforms for IO functions
defined in :py:class:`monai.transforms.io.array`.

Class names are ended with 'd' to denote dictionary-based transforms.
"""

from pathlib import Path
from typing import Optional, Union

import numpy as np

from monai.config import DtypeLike, KeysCollection
from monai.data import image_writer
from monai.data.image_reader import ImageReader
from monai.transforms.io.array import LoadImage, SaveImage
from monai.transforms.transform import MapTransform
from monai.utils import GridSampleMode, GridSamplePadMode, InterpolateMode, deprecated_arg
from monai.utils.enums import PostFix

__all__ = ["LoadImaged", "LoadImageD", "LoadImageDict", "SaveImaged", "SaveImageD", "SaveImageDict"]

DEFAULT_POST_FIX = PostFix.meta()


class LoadImaged(MapTransform):
    """
    Dictionary-based wrapper of :py:class:`monai.transforms.LoadImage`,
    It can load both image data and metadata. When loading a list of files in one key,
    the arrays will be stacked and a new dimension will be added as the first dimension
    In this case, the metadata of the first image will be used to represent the stacked result.
    The affine transform of all the stacked images should be same.
    The output metadata field will be created as ``meta_keys`` or ``key_{meta_key_postfix}``.

    If reader is not specified, this class automatically chooses readers
    based on the supported suffixes and in the following order:

        - User-specified reader at runtime when calling this loader.
        - User-specified reader in the constructor of `LoadImage`.
        - Readers from the last to the first in the registered list.
        - Current default readers: (nii, nii.gz -> NibabelReader), (png, jpg, bmp -> PILReader),
          (npz, npy -> NumpyReader), (dcm, DICOM series and others -> ITKReader).

    Note:

        - If `reader` is specified, the loader will attempt to use the specified readers and the default supported
          readers. This might introduce overheads when handling the exceptions of trying the incompatible loaders.
          In this case, it is therefore recommended setting the most appropriate reader as
          the last item of the `reader` parameter.

    See also:

        - tutorial: https://github.com/Project-MONAI/tutorials/blob/master/modules/load_medical_images.ipynb

    """

    @deprecated_arg(name="image_only", since="0.8")
    @deprecated_arg(name="meta_keys", since="0.8")
    @deprecated_arg(name="meta_key_postfix", since="0.8")
    @deprecated_arg(name="overwriting", since="0.8")
    def __init__(
        self,
        keys: KeysCollection,
        reader: Optional[Union[ImageReader, str]] = None,
        dtype: DtypeLike = np.float32,
        meta_keys: Optional[KeysCollection] = None,
        meta_key_postfix: str = DEFAULT_POST_FIX,
        overwriting: bool = False,
        image_only: bool = False,
        ensure_channel_first: bool = False,
        allow_missing_keys: bool = False,
        *args,
        **kwargs,
    ) -> None:
        """
        Args:
            keys: keys of the corresponding items to be transformed.
                See also: :py:class:`monai.transforms.compose.MapTransform`
            reader: reader to load image file and metadata
                - if `reader` is None, a default set of `SUPPORTED_READERS` will be used.
                - if `reader` is a string, it's treated as a class name or dotted path
                (such as ``"monai.data.ITKReader"``), the supported built-in reader classes are
                ``"ITKReader"``, ``"NibabelReader"``, ``"NumpyReader"``.
                a reader instance will be constructed with the `*args` and `**kwargs` parameters.
                - if `reader` is a reader class/instance, it will be registered to this loader accordingly.
            dtype: if not None, convert the loaded image data to this data type.
            ensure_channel_first: if `True` and loaded both image array and metadata, automatically convert
                the image array shape to `channel first`. default to `False`.
            allow_missing_keys: don't raise exception if key is missing.
            args: additional parameters for reader if providing a reader name.
            kwargs: additional parameters for reader if providing a reader name.
        """
        super().__init__(keys, allow_missing_keys)
        self._loader = LoadImage(reader, dtype, ensure_channel_first, *args, **kwargs)

    def register(self, reader: ImageReader):
        self._loader.register(reader)

    def __call__(self, data, reader: Optional[ImageReader] = None):
        """
        Raises:
            KeyError: When not ``self.overwriting`` and key already exists in ``data``.

        """
        d = dict(data)
        for key in self.key_iterator(d):
            d[key] = self._loader(d[key], reader)
        return d


class SaveImaged(MapTransform):
    """
    Dictionary-based wrapper of :py:class:`monai.transforms.SaveImage`.

    Note:
        Image should be channel-first shape: [C,H,W,[D]].
        If the data is a patch of big image, will append the patch index to filename.

    Args:
        keys: keys of the corresponding items to be transformed.
            See also: :py:class:`monai.transforms.compose.MapTransform`
        output_dir: output image directory.
        output_postfix: a string appended to all output file names, default to `trans`.
        output_ext: output file extension name, available extensions: `.nii.gz`, `.nii`, `.png`.
        output_dtype: data type for saving data. Defaults to ``np.float32``.
        resample: whether to resample image (if needed) before saving the data array,
            based on the `spatial_shape` (and `original_affine`) from metadata.
        mode: This option is used when ``resample=True``. Defaults to ``"nearest"``.
            Depending on the writers, the possible options are:

            - {``"bilinear"``, ``"nearest"``, ``"bicubic"``}.
              See also: https://pytorch.org/docs/stable/nn.functional.html#grid-sample
            - {``"nearest"``, ``"linear"``, ``"bilinear"``, ``"bicubic"``, ``"trilinear"``, ``"area"``}.
              See also: https://pytorch.org/docs/stable/nn.functional.html#interpolate

        padding_mode: This option is used when ``resample = True``. Defaults to ``"border"``.
            Possible options are {``"zeros"``, ``"border"``, ``"reflection"``}
            See also: https://pytorch.org/docs/stable/nn.functional.html#grid-sample
        scale: {``255``, ``65535``} postprocess data by clipping to [0, 1] and scaling
            [0, 255] (uint8) or [0, 65535] (uint16). Default is `None` (no scaling).
        dtype: data type during resampling computation. Defaults to ``np.float64`` for best precision.
            if None, use the data type of input data. To be compatible with other modules,
        output_dtype: data type for saving data. Defaults to ``np.float32``.
            it's used for NIfTI format only.
        allow_missing_keys: don't raise exception if key is missing.
        squeeze_end_dims: if True, any trailing singleton dimensions will be removed (after the channel
            has been moved to the end). So if input is (C,H,W,D), this will be altered to (H,W,D,C), and
            then if C==1, it will be saved as (H,W,D). If D is also 1, it will be saved as (H,W). If `false`,
            image will always be saved as (H,W,D,C).
        data_root_dir: if not empty, it specifies the beginning parts of the input file's
            absolute path. It's used to compute `input_file_rel_path`, the relative path to the file from
            `data_root_dir` to preserve folder structure when saving in case there are files in different
            folders with the same file names. For example, with the following inputs:

            - input_file_name: `/foo/bar/test1/image.nii`
            - output_postfix: `seg`
            - output_ext: `.nii.gz`
            - output_dir: `/output`
            - data_root_dir: `/foo/bar`

            The output will be: /output/test1/image/image_seg.nii.gz

        separate_folder: whether to save every file in a separate folder. For example: for the input filename
            `image.nii`, postfix `seg` and folder_path `output`, if `separate_folder=True`, it will be saved as:
            `output/image/image_seg.nii`, if `False`, saving as `output/image_seg.nii`. Default to `True`.
        print_log: whether to print logs when saving. Default to `True`.
        output_format: an optional string to specify the output image writer.
            see also: `monai.data.image_writer.SUPPORTED_WRITERS`.
        writer: a customised `monai.data.ImageWriter` subclass to save data arrays.
            if `None`, use the default writer from `monai.data.image_writer` according to `output_ext`.
            if it's a string, it's treated as a class name or dotted path;
            the supported built-in writer classes are ``"NibabelWriter"``, ``"ITKWriter"``, ``"PILWriter"``.

    """

    @deprecated_arg(name="meta_keys", since="0.8", msg_suffix="Use MetaTensor input")
    @deprecated_arg(name="meta_key_postfix", since="0.8", msg_suffix="Use MetaTensor input")
    def __init__(
        self,
        keys: KeysCollection,
        meta_keys: Optional[KeysCollection] = None,
        meta_key_postfix: str = DEFAULT_POST_FIX,
        output_dir: Union[Path, str] = "./",
        output_postfix: str = "trans",
        output_ext: str = ".nii.gz",
        resample: bool = True,
        mode: Union[GridSampleMode, InterpolateMode, str] = "nearest",
        padding_mode: Union[GridSamplePadMode, str] = GridSamplePadMode.BORDER,
        scale: Optional[int] = None,
        dtype: DtypeLike = np.float64,
        output_dtype: DtypeLike = np.float32,
        allow_missing_keys: bool = False,
        squeeze_end_dims: bool = True,
        data_root_dir: str = "",
        separate_folder: bool = True,
        print_log: bool = True,
        output_format: str = "",
        writer: Union[image_writer.ImageWriter, str, None] = None,
    ) -> None:
        super().__init__(keys, allow_missing_keys)
        self.saver = SaveImage(
            output_dir=output_dir,
            output_postfix=output_postfix,
            output_ext=output_ext,
            resample=resample,
            mode=mode,
            padding_mode=padding_mode,
            scale=scale,
            dtype=dtype,
            output_dtype=output_dtype,
            squeeze_end_dims=squeeze_end_dims,
            data_root_dir=data_root_dir,
            separate_folder=separate_folder,
            print_log=print_log,
            output_format=output_format,
            writer=writer,
        )

    def set_options(self, init_kwargs=None, data_kwargs=None, meta_kwargs=None, write_kwargs=None):
        self.saver.set_options(init_kwargs, data_kwargs, meta_kwargs, write_kwargs)

    def __call__(self, data):
        d = dict(data)
        for key in self.key_iterator(d):
            self.saver(img=d[key])
        return d


LoadImageD = LoadImageDict = LoadImaged
SaveImageD = SaveImageDict = SaveImaged
