# CyberRemesher NVIDIA CUDA runtime

Source is CyberdyneCorp/CyberRemesherAndUV v0.10.0 at the revision in manifest.json. The source ZIP is the codeload archive for that revision. Verify its SHA-256 before extracting. The Foundry changes are recorded in foundry-cuda.patch. They resolve MSVC portability errors and add an opt-in strict CUDA error path. The CLI is launched with that mode by Foundry.

The build used Visual Studio 2022 x64 toolset 14.44, CMake 3.31.10, Ninja 1.10.2 and CUDA 12.9.1 redist components nvcc 12.9.86, cudart 12.9.79 and CCCL 12.9.27. Use the official CUDA 12.9.1 redist manifest to verify those archives. Merge the compiler, runtime and header directories into one CUDA toolkit root for the build.

Apply the patch at the root of the extracted source and configure the upstream windows-cuda preset. Set CMAKE_CUDA_ARCHITECTURES to the semicolon-separated architecture list in manifest.json. Set CMAKE_CUDA_COMPILER and CUDAToolkit_ROOT to the chosen toolkit. Disable CYBER_BUILD_TESTS, CYBER_BUILD_NET, CYBER_BUILD_APP and CYBER_BUILD_CAPI. Set CYBER_WARNINGS_AS_ERRORS=OFF. Build target cyberremesh and copy the executable plus the pinned cudart64_12.dll to this directory. Verify --version and --list-backends on the target runtime. Update binary hashes only after verifying provenance and runtime behavior.

The package carries the engine license, third-party notices, ufbx license, CUDA runtime agreement and CCCL notices in licenses/pipeline. The application requires the Microsoft VC++ runtime and a compatible NVIDIA driver. Build-only tools remain outside the runtime package.

[Source release](https://github.com/CyberdyneCorp/CyberRemesherAndUV/releases/tag/v0.10.0) · [NVIDIA CUDA component manifest](https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.9.1.json)

