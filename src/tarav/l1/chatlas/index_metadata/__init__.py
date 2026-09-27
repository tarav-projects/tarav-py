"""Index-row metadata `Raw.Normalizer`s for `Normalization.Pipeline::Chatlas.Session.Model`.

The raw→index-metadata path: per-provider normalizers read the discovered session's raw
artifacts to produce the index row's raw-derived fields, replacing the agentos-py
`session_ref` extraction. `index_writer._session_index_row` calls `index_metadata`.
"""

from .assemble import index_metadata

__all__ = ["index_metadata"]
