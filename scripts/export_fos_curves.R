#!/usr/bin/env Rscript
# Export L111.RsrcCurves_EJ_R_Ffos from PREBUILT_DATA.rda
# to a CSV file for the GHIM Python energy module.
#
# Usage: Rscript scripts/export_fos_curves.R
# Output: ghim/data/external/energy/fos_curves_R32.csv

rda_path <- "input/gcamdata/data/PREBUILT_DATA.rda"
out_path <- "ghim/data/external/energy/fos_curves_R32.csv"

if (!file.exists(rda_path)) {
    stop("PREBUILT_DATA.rda not found at: ", rda_path)
}

# Load the .rda file into a temporary environment
env <- new.env()
load(rda_path, envir = env)

# Extract the fossil resource curves table
# PREBUILT_DATA.rda contains a single list object named PREBUILT_DATA
pbd <- env$PREBUILT_DATA
if (is.null(pbd) || !"L111.RsrcCurves_EJ_R_Ffos" %in% names(pbd)) {
    cat("Available names in PREBUILT_DATA:\n")
    print(names(pbd))
    stop("L111.RsrcCurves_EJ_R_Ffos not found in PREBUILT_DATA")
}

df <- pbd$L111.RsrcCurves_EJ_R_Ffos
cat(sprintf("Loaded L111.RsrcCurves_EJ_R_Ffos: %d rows x %d cols\n", nrow(df), ncol(df)))
cat("Columns:", paste(names(df), collapse = ", "), "\n")

# Write CSV
dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
write.csv(df, out_path, row.names = FALSE)
cat(sprintf("Exported to %s\n", out_path))

# Print summary
cat("\nResource types:\n")
print(table(df$resource))
cat("\nRows per region (first 10):\n")
print(head(table(df$GCAM_region_ID), 10))
