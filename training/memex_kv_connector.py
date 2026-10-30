#!/usr/bin/env python3
"""Memex custom vLLM KV connector (prototype).

Adapted from vLLM 0.10.2 `SharedStorageConnector` (Apache-2.0) to key cache
entries by a materialized-prefix length instead of the whole prompt. This lets
two requests with the same materialized context prefix but different final
questions load the prefix KV from external storage.

Usage (vLLM 0.10.2):
  PYTHONPATH=/root nohup python -m vllm.entrypoints.openai.api_server \
    --model /root/models/qwen --no-enable-prefix-caching \
    --kv-transfer-config '{"kv_connector":"MemexKVConnector","kv_role":"kv_both",
      "kv_connector_module_path":"memex_kv_connector",
      "kv_connector_extra_config":{"memex_kv_path":"/root/memex-kv","prefix_tokens":1500}}'

Limitations: fixed prefix length, disk storage, no block eviction beyond the
debug implementation; not production-ready.
"""
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import gzip
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import safetensors
import torch

from vllm.config import VllmConfig
from vllm.distributed.kv_transfer.kv_connector.v1.base import (
    KVConnectorBase_V1, KVConnectorMetadata, KVConnectorRole)
from vllm.logger import init_logger
from vllm.v1.attention.backends.mla.common import MLACommonMetadata
from vllm.v1.core.sched.output import SchedulerOutput

if TYPE_CHECKING:
    from vllm.attention.backends.abstract import AttentionMetadata
    from vllm.forward_context import ForwardContext
    from vllm.v1.core.kv_cache_manager import KVCacheBlocks
    from vllm.v1.request import Request

logger = init_logger(__name__)


@dataclass
class ReqMeta:
    # Request tokens
    token_ids: torch.Tensor
    # Slot mappings, should have the same length as token_ids
    slot_mapping: torch.Tensor
    # Is store or load
    is_store: bool
    mm_hashes: list[str]

    @staticmethod
    def make_meta(token_ids: list[int], block_ids: list[int], block_size: int,
                  is_store: bool, mm_hashes: list[str]) -> "ReqMeta":
        valid_num_tokens = len(token_ids)  # already block-aligned by scheduler
        token_ids_tensor = torch.tensor(token_ids)[:valid_num_tokens]
        block_ids_tensor = torch.tensor(block_ids)
        num_blocks = block_ids_tensor.shape[0]
        block_offsets = torch.arange(0, block_size)
        slot_mapping = block_offsets.reshape((1, block_size)) + \
                block_ids_tensor.reshape((num_blocks, 1)) * block_size
        slot_mapping = slot_mapping.flatten()[:valid_num_tokens]
        return ReqMeta(
            token_ids=token_ids_tensor,
            slot_mapping=slot_mapping,
            is_store=is_store,
            mm_hashes=mm_hashes,
        )


@dataclass
class MemexKVConnectorMetadata(KVConnectorMetadata):
    requests: list[ReqMeta]

    def __init__(self):
        self.requests = []

    def add_request(
        self,
        token_ids: list[int],
        block_ids: list[int],
        block_size: int,
        is_store: bool,
        mm_hashes: list[str],
    ) -> None:
        self.requests.append(
            ReqMeta.make_meta(token_ids, block_ids, block_size, is_store,
                              mm_hashes))


class MemexKVConnector(KVConnectorBase_V1):
    # NOTE: This is Simple debug implementation of the KV connector.
    # It save / load the KV cache to / from the disk.
    # It does extra work which will overwrite the existing prefix-cache in GPU
    # - to remove the overhead, need to add some "mask" in the ReqMeta class

    def __init__(self, vllm_config: "VllmConfig", role: KVConnectorRole):
        super().__init__(vllm_config=vllm_config, role=role)
        self._block_size = vllm_config.cache_config.block_size
        self._requests_need_load: dict[str, Request] = {}
        transfer_config = vllm_config.kv_transfer_config
        self._storage_path = transfer_config.get_from_extra_config(
            "memex_kv_path", "/root/memex-kv")
        self._prefix_tokens = int(transfer_config.get_from_extra_config(
            "prefix_tokens", 0) or 0)
        self._max_cache_mib = int(transfer_config.get_from_extra_config(
            "max_cache_mib", 2048) or 2048)
        self._compress = bool(transfer_config.get_from_extra_config(
            "compress", False))
        self._saved_folders = set()
        self._tenant_id = str(transfer_config.get_from_extra_config(
            "tenant_id", "default"))
        self._compress_level = int(transfer_config.get_from_extra_config(
            "compress_level", 9) or 9)
        self._min_prefix_tokens = int(transfer_config.get_from_extra_config(
            "min_prefix_tokens", 0) or 0)
        self._parallel_load = bool(transfer_config.get_from_extra_config(
            "parallel_load", True))
        logger.info(vllm_config.kv_transfer_config)
        logger.info("Shared storage path is %s", self._storage_path)

    def _prefix_len(self, request) -> int:
        """Number of leading prompt tokens that form the materialized prefix."""
        limit = len(request.prompt_token_ids) - 1
        want = self._prefix_tokens if self._prefix_tokens > 0 else limit
        return min(limit, want)

    def _external_enabled(self, request) -> bool:
        """Hybrid routing: short prompts stay on the native prefix cache."""
        return len(request.prompt_token_ids) >= self._min_prefix_tokens

    def _prefix_block_ids(self, request, block_ids):
        prefix = self._prefix_tokens
        need = (prefix + self._block_size - 1) // self._block_size
        return list(block_ids[:need])

    def start_load_kv(self, forward_context: "ForwardContext",
                      **kwargs) -> None:
        """Start loading the KV cache from the connector buffer to vLLM's 
        paged KV buffer.

        Args:
            forward_context (ForwardContext): the forward context.
            **kwargs: additional arguments for the load operation

        Note:
            The number of elements in kv_caches and layer_names should be 
            the same.
        """
        attn_metadata = forward_context.attn_metadata

        def inject_kv_into_layer(
            dst_kv_cache_layer: torch.Tensor,
            src_kv_cache: torch.Tensor,
            slot_mapping: torch.Tensor,
        ) -> None:
            """Inject the KV cache into the layer.

            Args:
                dst_kv_cache_layer (torch.Tensor): the destination KV cache 
                    layer. In shape [2, num_pages, page_size, xxx] if not 
                    using MLA, [num_pages, page_size, xxx] otherwise.
                src_kv_cache (torch.Tensor): the source KV cache. In shape
                    [2, num_tokens, xxx] if not using MLA, [num_tokens, xxx] 
                    otherwise.
                slot_mapping (torch.Tensor): the slot mapping. In shape 
                    [num_tokens].
            """
            dst_kv_cache_layer_shape = dst_kv_cache_layer.shape
            if isinstance(attn_metadata, MLACommonMetadata):
                num_pages = dst_kv_cache_layer_shape[0]
                page_size = dst_kv_cache_layer_shape[1]
                dst_kv_cache_layer = dst_kv_cache_layer.reshape(
                    num_pages * page_size, -1)
                dst_kv_cache_layer[slot_mapping, ...] = src_kv_cache
                dst_kv_cache_layer.reshape(dst_kv_cache_layer_shape)
            else:
                num_pages = dst_kv_cache_layer_shape[1]
                page_size = dst_kv_cache_layer_shape[2]
                dst_kv_cache_layer = dst_kv_cache_layer.reshape(
                    2, num_pages * page_size, -1)
                dst_kv_cache_layer[:, slot_mapping, ...] = src_kv_cache
                dst_kv_cache_layer.reshape(dst_kv_cache_layer_shape)

        # Get the metadata
        metadata: KVConnectorMetadata = self._get_connector_metadata()
        assert isinstance(metadata, MemexKVConnectorMetadata)

        if metadata is None:
            logger.warning(
                "In connector.start_load_kv, but the connector metadata is None"
            )
            return

        attn_metadata = forward_context.attn_metadata
        if attn_metadata is None:
            logger.warning(
                "In connector.start_load_kv, but the attn_metadata is None")
            return

        # Load the KV for each request each layer
        for request in metadata.requests:
            if request.is_store:
                continue
            logger.warning("MEMEX inject KV tokens=%d", len(request.slot_mapping))
            layers = []
            for layer_name in forward_context.no_compile_layers:
                layer = forward_context.no_compile_layers[layer_name]
                kv_cache_attr = getattr(layer, 'kv_cache', None)
                if kv_cache_attr is None:
                    continue
                layers.append((layer_name, kv_cache_attr[forward_context.virtual_engine]))
            if not layers:
                continue
            filenames = [self._generate_filename_debug(name, request.token_ids, request.mm_hashes) for name, _ in layers]
            def load_one(filename):
                if self._compress:
                    with gzip.open(filename, "rb") as handle:
                        return safetensors.torch.load(handle.read())["kv_cache"].cuda()
                return safetensors.torch.load_file(filename)["kv_cache"].cuda()
            # Batch/parallel layer-file load; helps many-layer models.
            if self._parallel_load:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    tensors = list(pool.map(load_one, filenames))
            else:
                tensors = [load_one(filename) for filename in filenames]
            for (_layer_name, kv_cache_layer), kv_cache in zip(layers, tensors):
                inject_kv_into_layer(kv_cache_layer, kv_cache, request.slot_mapping)

    def wait_for_layer_load(self, layer_name: str) -> None:
        """Blocking until the KV for a specific layer is loaded into vLLM's
        paged buffer. 
        
        This interface will be useful for layer-by-layer pipelining.

        Args:
            layer_name: the name of that layer
        """
        return

    def save_kv_layer(self, layer_name: str, kv_layer: torch.Tensor,
                      attn_metadata: "AttentionMetadata", **kwargs) -> None:
        """Start saving the KV cache of the layer from vLLM's paged buffer 
        to the connector.

        Args:
            layer_name (str): the name of the layer.
            kv_layer (torch.Tensor): the paged KV buffer of the current 
                layer in vLLM.
            attn_metadata (AttentionMetadata): the attention metadata.
            **kwargs: additional arguments for the save operation.
        """

        def extract_kv_from_layer(
            layer: torch.Tensor,
            slot_mapping: torch.Tensor,
        ) -> torch.Tensor:
            """Extract the KV cache from the layer.

            Assume the shape of the layer is (2, num_pages, page_size, xxx)
            if MLA is not used, and (num_pages, page_size, xxx) otherwise.
            """
            if isinstance(attn_metadata, MLACommonMetadata):
                num_pages, page_size = layer.shape[0], layer.shape[1]
                return layer.reshape(num_pages * page_size, -1)[slot_mapping,
                                                                ...]
            num_pages, page_size = layer.shape[1], layer.shape[2]
            return layer.reshape(2, num_pages * page_size, -1)[:, slot_mapping,
                                                               ...]

        connector_metadata = self._get_connector_metadata()
        assert isinstance(connector_metadata, MemexKVConnectorMetadata)
        for request in connector_metadata.requests:
            if request.is_store:
                filename = self._generate_filename_debug(
                    layer_name, request.token_ids, request.mm_hashes)
                kv_cache = extract_kv_from_layer(kv_layer,
                                                 request.slot_mapping)
                logger.warning("MEMEX store KV tokens=%d layer=%s", len(request.slot_mapping), layer_name)
                tensors = {"kv_cache": kv_cache.detach().cpu()}
                if self._compress:
                    with gzip.open(filename, "wb") as handle:
                        handle.write(safetensors.torch.save(tensors))
                else:
                    safetensors.torch.save_file(tensors, filename)
                self._saved_folders.add(os.path.dirname(filename))

    def wait_for_save(self):
        for folder in list(self._saved_folders):
            self._write_manifest(folder)
        self._saved_folders.clear()
        self._evict_cache()

    def _write_manifest(self, folder):
        if not os.path.isdir(folder):
            return
        files = {}
        for name in os.listdir(folder):
            if name.endswith('.safetensors') or name.endswith('.safetensors.gz'):
                files[name] = os.path.getsize(os.path.join(folder, name))
        manifest = {'version': 2, 'tenant_id': self._tenant_id, 'token_count': self._prefix_tokens,
                    'compressed': self._compress, 'compress_level': self._compress_level, 'files': files}
        try:
            with open(os.path.join(folder, 'manifest.json'), 'w') as handle:
                json.dump(manifest, handle)
        except OSError:
            pass

    def _evict_cache(self):
        """Bound the external KV directory by evicting the oldest prefix folders."""
        if self._max_cache_mib <= 0:
            return
        entries = []
        total = 0
        for name in os.listdir(self._storage_path):
            folder = os.path.join(self._storage_path, name)
            if not os.path.isdir(folder):
                continue
            size = 0
            for root, _dirs, files in os.walk(folder):
                for filename in files:
                    try:
                        size += os.path.getsize(os.path.join(root, filename))
                    except OSError:
                        pass
            entries.append((os.path.getmtime(folder), size, folder))
            total += size
        limit = self._max_cache_mib * 1024 * 1024
        for _mtime, size, folder in sorted(entries):
            if total <= limit:
                break
            logger.warning("MEMEX evict prefix cache %.1f MiB: %s", size / 1024 / 1024, folder)
            for root, _dirs, files in os.walk(folder, topdown=False):
                for filename in files:
                    try:
                        os.remove(os.path.join(root, filename))
                    except OSError:
                        pass
                try:
                    os.rmdir(root)
                except OSError:
                    pass
            total -= size

    def get_num_new_matched_tokens(
        self,
        request: "Request",
        num_computed_tokens: int,
    ) -> tuple[Optional[int], bool]:
        """
        Get number of new tokens that can be loaded from the
        external KV cache beyond the num_computed_tokens.
        
        Args:
            request (Request): the request object.
            num_computed_tokens (int): the number of locally
                computed tokens for this request

        Returns:
            the number of tokens that can be loaded from the 
            external KV cache beyond what is already computed.
        """
        # NOTE: in this debug implementation, we assume that the prompt is
        # cached_prompt + newly_generated_single_token
        # Therefore, we use prompt_token_ids[:-1] to determine the folder name

        # NOTE: in current v1 scheduler, the num_computed_tokens is aligned
        # with the block granularity. And it expects the returned blocks and
        # num_computed_tokens to also be aligned with the block granularity.
        if num_computed_tokens > 0:
            # Native prefix cache already serves this prefix; avoid external disk load.
            return 0, False
        if not self._external_enabled(request) or not self._found_match_for_request(request):
            return 0, False

        logger.warning("MEMEX EXTERNAL CACHE HIT prefix_tokens=%s", self._prefix_tokens)

        # Now, first num_tokens_to_check tokens are hit, we need to prepare
        # the metadata for the worker connector to correctly load the KV
        num_tokens_to_check = align_to_block_size(
            self._prefix_len(request), self._block_size)

        return num_tokens_to_check - num_computed_tokens, False

    def update_state_after_alloc(self, request: "Request",
                                 blocks: "KVCacheBlocks",
                                 num_external_tokens: int):
        """
        Update KVConnector state after block allocation.

        If blocks were allocated, add to _requests_need_load,
        such that we load the KVs in the next forward pass.
        """
        if num_external_tokens > 0:
            self._requests_need_load[request.request_id] = request

    def build_connector_meta(
        self,
        scheduler_output: SchedulerOutput,
    ) -> KVConnectorMetadata:
        """Build the connector metadata for this step.

        This function should NOT modify any fields in the scheduler_output.
        Also, calling this function will reset the state of the connector.

        Args:
            scheduler_output (SchedulerOutput): the scheduler output object.
        """
        meta = MemexKVConnectorMetadata()

        total_need_load = 0
        for new_req in scheduler_output.scheduled_new_reqs:
            if new_req.req_id in self._requests_need_load:
                prefix_len = align_to_block_size(self._prefix_len(new_req), self._block_size)
                meta.add_request(token_ids=new_req.prompt_token_ids[:prefix_len],
                                 block_ids=self._prefix_block_ids(new_req, new_req.block_ids[0]),
                                 block_size=self._block_size,
                                 is_store=False,
                                 mm_hashes=new_req.mm_hashes)
                total_need_load += 1
            else:
                # NOTE: here, we set the store and load being exclusive,
                # but a single request can have both store and load.
                # NOTE(rob): for this debug implementation, we only cache
                # the original prompt tokens.
                if self._external_enabled(new_req) and not self._found_match_for_request(new_req):
                    prefix_len = align_to_block_size(self._prefix_len(new_req), self._block_size)
                    meta.add_request(token_ids=new_req.prompt_token_ids[:prefix_len],
                                     block_ids=self._prefix_block_ids(new_req, new_req.block_ids[0]),
                                     block_size=self._block_size,
                                     is_store=True,
                                     mm_hashes=new_req.mm_hashes)

        cached_reqs = scheduler_output.scheduled_cached_reqs
        for i, req_id in enumerate(cached_reqs.req_ids):
            num_computed_tokens = cached_reqs.num_computed_tokens[i]
            num_new_tokens = scheduler_output.num_scheduled_tokens[req_id]
            new_block_ids = cached_reqs.new_block_ids[i]
            resumed_from_preemption = cached_reqs.resumed_from_preemption[i]

            # NOTE(rob): here we rely on the resumed requests being
            # the first N requests in the list scheduled_cache_reqs.
            if not resumed_from_preemption:
                break
            if req_id in self._requests_need_load:
                # NOTE(rob): cached_req_data does not have the full
                # list of token ids (only new tokens). So we look it
                # up in the actual request object.
                request = self._requests_need_load[req_id]
                total_tokens = num_computed_tokens + num_new_tokens
                token_ids = request.all_token_ids[:total_tokens]

                # NOTE(rob): For resumed req, new_block_ids is all
                # of the block_ids for the request.
                block_ids = new_block_ids[0]

                meta.add_request(token_ids=token_ids,
                                 block_ids=block_ids,
                                 block_size=self._block_size,
                                 is_store=False,
                                 mm_hashes=request.mm_hashes)
                total_need_load += 1

        assert total_need_load == len(self._requests_need_load)
        self._requests_need_load.clear()
        return meta

    # ==============================
    # Helper functions
    # ==============================

    def _found_match_for_request(
        self,
        request: "Request",
    ) -> bool:
        """Check if the cache is hit for the request."""
        if not self._external_enabled(request):
            return False
        num_tokens_to_check = align_to_block_size(
            self._prefix_len(request), self._block_size)
        foldername = self._generate_foldername_debug(torch.tensor(
            request.prompt_token_ids[:num_tokens_to_check]),
                                                     request.mm_hashes,
                                                     create_folder=False)
        exists = os.path.exists(foldername)
        if exists:
            try:
                manifest = json.load(open(os.path.join(foldername, 'manifest.json')))
                if manifest.get('tenant_id', 'default') != self._tenant_id:
                    raise ValueError('tenant mismatch')
                for name, size in manifest.get('files', {}).items():
                    path = os.path.join(foldername, name)
                    if not os.path.exists(path) or os.path.getsize(path) != size:
                        raise ValueError(f'bad {name}')
                    if name.endswith('.gz'):
                        with open(path, 'rb') as handle:
                            if handle.read(2) != b'\x1f\x8b':
                                raise ValueError('bad gzip magic')
            except Exception as error:
                logger.warning("MEMEX invalid cache %s: %s; evicting", foldername, error)
                shutil.rmtree(foldername, ignore_errors=True)
                exists = False
        logger.warning("MEMEX match prefix_len=%d folder=%s exists=%s", num_tokens_to_check, foldername, exists)
        return exists

    def _generate_foldername_debug(
        self,
        token_ids: torch.Tensor,
        mm_hashes: list[str],
        create_folder=False,
    ) -> str:
        """Generate a folder name based on the hash of the bytes of the input 
        ids.
        """
        token_bytes = token_ids.numpy().tobytes()
        # Add mm_hashes to the bytes being hashed to avoid path traversal and
        # to create a canonical key.
        token_bytes += self._tenant_id.encode('utf-8')
        if mm_hashes:
            mm_str = "-".join(mm_hashes)
            token_bytes += mm_str.encode('utf-8')
        input_ids_hash = hashlib.md5(token_bytes,
                                     usedforsecurity=False).hexdigest()

        foldername = os.path.join(self._storage_path, input_ids_hash)
        if create_folder:
            os.makedirs(foldername, exist_ok=True)
        return foldername

    def _generate_filename_debug(
        self,
        layer_name: str,
        token_ids: torch.Tensor,
        mm_hashes: list[str],
    ) -> str:
        """Generate a file name based on the layer name and the hash 
        of the bytes of the input ids.
        """
        foldername = self._generate_foldername_debug(token_ids,
                                                     mm_hashes=mm_hashes,
                                                     create_folder=True)
        return os.path.join(foldername, f"{layer_name}.safetensors" + (".gz" if self._compress else ""))


def align_to_block_size(num_tokens: int, block_size) -> int:
    """Align the number of tokens to the block size.
    """
    return (num_tokens - 1) // block_size * block_size
