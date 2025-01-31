# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Quantization-ready quantizers.
"""

from typing import Optional

import torch
from torch._C import dtype
from torch.quantization import MinMaxObserver

from archai.nlp.quantization.observers import OnnxDynamicObserver


class FakeDynamicQuant(torch.nn.Module):
    """Inserts a fake dynamic quantizer to allow for a proper scale/zero point calculating
    when performing Quantization Aware Training.

    """

    def __init__(
        self,
        reduce_range: Optional[bool] = True,
        dtype: Optional[dtype] = torch.quint8,
        bits: Optional[int] = 8,
        onnx_compatible: Optional[bool] = False,
    ) -> None:
        """Initializes a customizable operator for inserting a fake dynamic quantizer.

        Args:
            reduce_range: Whether to reduce the range of quantization.
            dtype: Type of quantization operators.
            bits: Number of bits used in the quantization.
            onnx_compatible: Whether quantization is compatible with ONNX.

        """

        super().__init__()

        self.bits = bits
        self.reduce_range = reduce_range if bits == 8 else False
        self.dtype = dtype
        self.onnx_compatible = onnx_compatible

        assert dtype in (torch.quint8, torch.qint8)

        if dtype == torch.quint8:
            if self.reduce_range:
                self.qmin, self.qmax = 0, 2 ** (bits - 1)
            else:
                self.qmin, self.qmax = 0, 2**bits - 1

        else:
            if self.reduce_range:
                self.qmin, self.qmax = -(2 ** (bits - 2)), 2 ** (bits - 2) - 1
            else:
                self.qmin, self.qmax = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Performs a forward pass over the fake dynamic quantization module.

        Args:
            x: Input tensor.

        Returns:
            (torch.Tensor): Fake dynamically quantized tensor.

        """

        if x.dtype == torch.float32:
            if self.bits == 8:
                if self.dtype == torch.quint8:
                    qscheme = torch.per_tensor_affine
                else:
                    qscheme = torch.per_tensor_symmetric

                if self.onnx_compatible:
                    observer = OnnxDynamicObserver(dtype=self.dtype)
                else:
                    observer = MinMaxObserver(
                        dtype=self.dtype,
                        qscheme=qscheme,
                        reduce_range=self.reduce_range,
                    )

                observer(x)
                scale, zero_pointer = observer.calculate_qparams()

            else:
                min_val, max_val = x.min(), x.max()
                initial_scale = (max_val - min_val) / float(self.qmax - self.qmin)

                min_zero_pointer = self.qmin - min_val / initial_scale
                max_zero_pointer = self.qmax - max_val / initial_scale
                min_zero_pointer_error = abs(self.qmin) - abs(min_val / initial_scale)
                max_zero_pointer_error = abs(self.qmax) - abs(max_val / initial_scale)

                if min_zero_pointer_error < max_zero_pointer_error:
                    initial_zero_pointer = min_zero_pointer
                else:
                    initial_zero_pointer = max_zero_pointer
                initial_zero_pointer = initial_zero_pointer.round()

                scale, zero_pointer = initial_scale, initial_zero_pointer

            x = torch.fake_quantize_per_tensor_affine(
                x, float(scale.item()), int(zero_pointer.item()), self.qmin, self.qmax
            )

            self._scale, self._zero_pointer = scale, zero_pointer

        return x
