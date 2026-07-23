args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("usage: Rscript validate_pairing_abs_v16.R <output.csv>")
}

values <- data.frame(
  case_id = seq_len(6),
  treatment = c(-3, 2, 0, NA, 5, -7),
  control = c(1, -5, 0, 4, NA, -7)
)

values$abs_treatment <- abs(values$treatment)
values$abs_control <- abs(values$control)
values$abs_difference <- abs(values$treatment - values$control)
values$abs_relative <- abs((values$treatment - values$control) / values$control)

numeric_columns <- c(
  "abs_treatment",
  "abs_control",
  "abs_difference",
  "abs_relative"
)
for (column in numeric_columns) {
  values[[column]][!is.finite(values[[column]])] <- NA_real_
}

write.csv(values, args[[1]], row.names = FALSE, na = "")
cat(R.version.string, "\n")
