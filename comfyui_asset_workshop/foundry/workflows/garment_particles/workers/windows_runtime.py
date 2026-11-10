"""Windows compatibility limited to the standalone Garment Particles worker."""
from contextlib import nullcontext
import importlib.util
from importlib.machinery import ModuleSpec
import pathlib
import pickle
import sys
from types import ModuleType

import torch
from torch.distributed.checkpoint import FileSystemReader
from torch.distributed.checkpoint.metadata import StorageMeta
from torch.nn import functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel


class PortableMetadata(pickle.Unpickler):
    def find_class(self, module, name):
        # Torch serializes checkpoint bookkeeping paths from the source OS.
        if module == 'pathlib' and name == 'PosixPath':
            return pathlib.PurePosixPath
        return super().find_class(module, name)


class PortableCheckpointReader(FileSystemReader):
    def read_metadata(self, *args, **kwargs):
        path = self._get_metadata_path(kwargs.get('rank'))
        with self.fs.create_stream(path, 'rb') as stream:
            metadata = PortableMetadata(stream).load()
        if metadata.storage_meta is None:
            metadata.storage_meta = StorageMeta()
        metadata.storage_meta.load_id = self.load_id
        return metadata


def sdpa(q, k, v, dropout=0.0, causal=False, window_size=(-1, -1)):
    if tuple(window_size) != (-1, -1):
        raise ValueError('This Garment Particles recipe expects full attention.')
    # Keep long garment sequences off the quadratic math backend on CUDA.
    backend = sdpa_kernel([SDPBackend.FLASH_ATTENTION, SDPBackend.EFFICIENT_ATTENTION,
                           SDPBackend.CUDNN_ATTENTION]) if q.is_cuda else nullcontext()
    with backend:
        result = F.scaled_dot_product_attention(
            q.transpose(-3, -2), k.transpose(-3, -2), v.transpose(-3, -2),
            dropout_p=dropout, is_causal=causal)
    return result.transpose(-3, -2).contiguous()


def varlen(q, k, v, cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k,
           dropout_p=0.0, causal=False, window_size=(-1, -1)):
    q_offsets = cu_seqlens_q.tolist()
    k_offsets = cu_seqlens_k.tolist()
    if len(q_offsets) != len(k_offsets):
        raise ValueError('Garment attention batches have mismatched lengths.')
    out = []
    for q_start, q_end, k_start, k_end in zip(q_offsets[:-1], q_offsets[1:], k_offsets[:-1], k_offsets[1:]):
        out.append(sdpa(q[None, q_start:q_end], k[None, k_start:k_end], v[None, k_start:k_end],
                        dropout_p, causal, window_size)[0])
    return torch.cat(out)


def varlen_qkv(qkv, cu_seqlens, max_seqlen, **kwargs):
    q, k, v = qkv.unbind(1)
    return varlen(q, k, v, cu_seqlens, cu_seqlens, max_seqlen, max_seqlen, **kwargs)


def varlen_kv(q, kv, **kwargs):
    k, v = kv.unbind(1)
    return varlen(q, k, v, **kwargs)


def pad_input(values, indices, batch_size, sequence_length):
    out = values.new_zeros((batch_size * sequence_length, *values.shape[1:]))
    out.index_copy_(0, indices, values)
    return out.reshape(batch_size, sequence_length, *values.shape[1:])


def unpad_input(values, mask):
    lengths = mask.sum(dim=-1, dtype=torch.int32)
    indices = mask.flatten().nonzero().flatten()
    return (values.flatten(0, 1).index_select(0, indices), indices,
            F.pad(lengths.cumsum(0, dtype=torch.int32), (1, 0)), lengths.max().item())


def configure_attention():
    if importlib.util.find_spec('flash_attn') is not None:
        return
    flash = ModuleType('flash_attn')
    flash.__spec__ = ModuleSpec('flash_attn', loader=None, is_package=True)
    flash.flash_attn_func = sdpa
    flash.flash_attn_qkvpacked_func = lambda qkv, *args, **kwargs: sdpa(*qkv.unbind(-3), *args, **kwargs)
    flash.flash_attn_kvpacked_func = lambda q, kv, *args, **kwargs: sdpa(q, *kv.unbind(-3), *args, **kwargs)
    flash.flash_attn_varlen_func = varlen
    flash.flash_attn_varlen_qkvpacked_func = varlen_qkv
    flash.flash_attn_varlen_kvpacked_func = varlen_kv
    padding = ModuleType('flash_attn.bert_padding')
    padding.__spec__ = ModuleSpec('flash_attn.bert_padding', loader=None)
    padding.index_first_axis = lambda values, indices: values.index_select(0, indices)
    padding.pad_input = pad_input
    padding.unpad_input = unpad_input
    flash.bert_padding = padding
    sys.modules.update({'flash_attn': flash, 'flash_attn.bert_padding': padding})
