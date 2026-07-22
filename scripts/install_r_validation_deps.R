#!/usr/bin/env Rscript

# Install development-only R comparison packages into a project-local library.
args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args)) normalizePath(args[[1]], winslash = "/", mustWork = TRUE) else normalizePath(".", winslash = "/", mustWork = TRUE)
target <- file.path(root, ".r-validation-lib")
dir.create(target, recursive = TRUE, showWarnings = FALSE)
packages <- c("jsonlite", "car", "emmeans", "DescTools", "irr", "exact2x2", "lme4")
installed <- rownames(installed.packages(lib.loc = target))
missing <- setdiff(packages, installed)
if (length(missing)) install.packages(missing, lib = target, repos = "https://cloud.r-project.org", Ncpus = 2)
cat("R validation library:", target, "\n")
cat("Available:", paste(packages, collapse = ", "), "\n")
