# Dependency licenses

Checked 2026-11-01 against PyPI metadata (SPDX expression or classifier).
This repo is MIT; everything below is permissive, so MIT stays.

| Package | Role | License |
| --- | --- | --- |
| docling | PDF/image conversion, OCR | MIT |
| markitdown | Office/HTML conversion | MIT |
| trafilatura | Article extraction | Apache-2.0 |
| youtube-transcript-api | YouTube captions | MIT |
| yt-dlp | Subtitles / audio download | Unlicense |
| faster-whisper | Local transcription (optional) | MIT |
| fitdecode / fitparse | FIT parsing | MIT |
| gpxpy | GPX output | Apache-2.0 |
| fastapi / pydantic | API and models | MIT |
| uvicorn | Server | BSD-3-Clause |
| garminconnect (unofficial fallback) | Garmin login client | MIT |

Method: a pip dry-run resolved 149 packages for the set above (docling,
markitdown, trafilatura, youtube-transcript-api, yt-dlp, faster-whisper,
fitdecode, gpxpy, fastapi, uvicorn); every package's license was
queried and flagged if GPL/AGPL/LGPL/non-commercial/unknown.

Frontend (checked 2026-11-01 with `npm view`): leaflet BSD-2-Clause, uPlot
MIT, @types/leaflet MIT. React, Vite and TypeScript are the usual
MIT/MIT/Apache-2.0 (not re-queried). Map tiles come from OpenStreetMap
(ODbL data; attribution shown in the map). OSM's tile usage policy applies
to heavy use and has not been reviewed here.

Findings:

- **`tld`** (via trafilatura's dependency chain): `MPL-1.1 OR GPL-2.0-only
  OR LGPL-2.1-or-later`. A choice of licenses; using it as an unmodified
  dependency under MPL/LGPL is compatible.
- **NVIDIA CUDA packages** (`cuda-toolkit`, `nvidia-cudnn-*`,
  `nvidia-nccl-*`, `nvidia-nvshmem-*`): no license in metadata; NVIDIA's
  own proprietary terms. They arrive through PyTorch (via docling).
  Avoid them in the Docker image by installing CPU-only PyTorch.
- No AGPL/GPL-only package appeared in the resolved set.

Not checked (follow up before a release):

- **Model weights** that Docling downloads (layout/OCR/table models) have
  their own licenses, separate from the package licenses.
- **Garmin's official client**
  ([garmin/connect-personal-api-python](https://github.com/garmin/connect-personal-api-python)):
  license not read. We can call the documented HTTP endpoints directly
  instead of depending on it.
- **DuckDB** (if chosen): the PyPI license field was empty; I believe it
  is MIT but did not verify.
- Garmin's FIT SDK is a separate Garmin-licensed product; use
  fitdecode/fitparse (MIT) instead.
