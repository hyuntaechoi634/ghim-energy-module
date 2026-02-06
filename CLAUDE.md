# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GCAM (Global Change Analysis Model) is a dynamic-recursive multisector integrated assessment model developed by JGCRI/PNNL. It models the economy, energy sector, land use, water, and climate systems across 32 geopolitical regions from 1990-2100 at 5-year intervals.

## Architecture

The codebase has two major components:

### C++ Core Model (`cvs/objects/`)
The simulation engine organized into ~20 modules under `cvs/objects/`:
- **marketplace/** - Supply-demand equilibrium solver (market clearing)
- **sectors/** - Energy, agriculture, industrial sector representations
- **technologies/** - Energy conversion and end-use technology modules
- **solution/** - Solver infrastructure (solvers/ and util/ subdirectories)
- **climate/** - Hector climate model integration (git submodule)
- **containers/** - Core data containers and scenario management
- **land_allocator/** - Land use allocation across 384 sub-regions
- **resources/** - Resource supply curves
- **emissions/** - GHG and pollutant emissions calculations
- **demographics/** - Population modeling
- **consumers/** - Consumer behavior with nested logit choice
- **functions/** - Mathematical/economic functions
- **parallel/** - TBB-based parallelization
- **main/** - Entry point, compiles to `exe/gcam.exe`

Each module follows the pattern: `cvs/objects/<module>/source/*.cpp` (implementation) and `cvs/objects/<module>/include/*.h` (headers).

### R Data Processing Package (`input/gcamdata/`)
An R package (gcamdata v8.2) that transforms raw input data into XML configuration files consumed by the C++ model:
- **R/** - ~450 chunk files, each a modular data processing unit declaring inputs/outputs
- Uses Drake workflow framework for dependency management and caching
- Chunk naming convention: `module_<sector>_<description>.R`
- Output: XML files written to `xml/` subdirectories

### Data Flow
```
Raw CSV/RDA data → R gcamdata chunks → XML config files → GCAM C++ executable → BaseX XML database
```

## Build Commands

### C++ Model
```bash
make gcam                    # Build GCAM executable (output: exe/gcam.exe)
make clean                   # Clean all build artifacts
make gcam-prof               # Build with profiling (-pg)
make install_hector          # Initialize Hector climate submodule
make varchk                  # Debug: print all build variable values
```

The build delegates to `cvs/objects/build/linux/Makefile`. Build configuration:
- `cvs/objects/build/linux/config.system` - System-specific library paths
- `cvs/objects/build/linux/configure.gcam` - Compiler flags, feature toggles

Required environment variables: `BOOST_INCLUDE`, `EIGEN_INCLUDE`, `TBB_INCLUDE`, `TBB_LIB`, `JAVA_INCLUDE`, `JAVA_LIB`, `JARS_LIB`. Set `HAVE_JAVA=0` in configure.gcam to build without Java/BaseX output.

### R Data Processing
```bash
make xml                     # Generate XML input files
make drake                   # Run full Drake workflow (with caching)

# Or directly:
cd input/gcamdata
Rscript -e "devtools::load_all('.')" -e "driver(write_output=FALSE, write_xml=TRUE)"
Rscript -e "devtools::load_all('.')" -e "driver_drake()"
```

R dependencies are managed via `renv`. To restore: `Rscript -e "renv::restore()"` from `input/gcamdata/`.

### Running the Model
```bash
cd exe && ./gcam.exe         # Run with default configuration
```

Configuration files: `exe/configuration_ref.xml`, `exe/configuration_policy.xml`, and various `exe/batch_*.xml` for scenario batches.

## Testing

### R Package Tests
```bash
cd input/gcamdata
Rscript -e "devtools::test()"                    # Run all tests
Rscript -e "testthat::test_file('tests/testthat/test_chunks.R')"  # Single test file
```

Tests are in `input/gcamdata/tests/testthat/` (19 test files using testthat framework).

CI runs `rcmdcheck::rcmdcheck(args = c("--no-manual", "--ignore-vignettes"), error_on = "error")` on PR via GitHub Actions against R 3.6.3 and latest release.

## Key Configuration

- C++ standard: C++17 (fallback C++14 via `NO_CXX17`)
- Parallelization: TBB enabled by default (`USE_GCAM_PARALLEL=1`)
- Climate model: Hector enabled by default (`USE_HECTOR=1`), submodule at `cvs/objects/climate/source/hector`
- MKL: Optional, auto-detected from `MKL_CFLAGS` environment variable

## Git Submodules

- **Hector**: `cvs/objects/climate/source/hector` (branch: gcam-integrationv3)
- **Model Interface**: `output/modelinterface/modelinterface`
- **Testing Framework**: `util/testing-framework/`

## Contribution Process

PRs target feature branches on JGCRI/gcam-core. Branch naming: `feature/` or `bugfix/` prefix. PRs require a GCAM Core Model Proposal document describing purpose, methods, and verification.
