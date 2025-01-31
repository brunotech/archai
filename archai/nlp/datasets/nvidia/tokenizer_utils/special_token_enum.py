# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Special tokens enumerator.
"""

from enum import Enum


class SpecialTokenEnum(Enum):
    """Implements an enumerator for special tokens."""

    UNK = 0
    BOS = 1
    EOS = 2
    PAD = 3
    MASK = 4
