args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("usage: Rscript validate_derived_split_factor.R <input.csv> <output-dir>")
}

input_path <- args[[1]]
output_dir <- args[[2]]
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

data <- read.csv(input_path, stringsAsFactors = FALSE, check.names = FALSE)
data$平均值 <- round((data$x1 + data$x2) / 2, 8)
data$比率 <- round(data$x2 / data$x1, 8)
data$比率[!is.finite(data$比率)] <- NA_real_

write.csv(
  data[c("id", "平均值", "比率")],
  file.path(output_dir, "derived_values.csv"),
  row.names = FALSE,
  na = ""
)

data$split_group <- ifelse(
  data$factor %in% c("A", "B"), "前组",
  ifelse(data$factor %in% c("C", "D"), "后组", NA_character_)
)
assigned <- data[!is.na(data$split_group), ]

summary_rows <- do.call(rbind, lapply(split(assigned, assigned$split_group), function(part) {
  data.frame(
    split_group = unique(part$split_group),
    n = nrow(part),
    factor_levels = length(unique(part$factor)),
    outcome_mean = mean(part$outcome),
    derived_mean = mean(part$平均值),
    stringsAsFactors = FALSE
  )
}))
write.csv(summary_rows, file.path(output_dir, "split_summary.csv"), row.names = FALSE)

anova_rows <- do.call(rbind, lapply(split(assigned, assigned$split_group), function(part) {
  part$factor <- factor(part$factor)
  table <- summary(aov(outcome ~ factor, data = part))[[1]]
  data.frame(
    split_group = unique(part$split_group),
    df_num = unname(table["factor", "Df"]),
    df_den = unname(table["Residuals", "Df"]),
    f_value = unname(table["factor", "F value"]),
    p_value = unname(table["factor", "Pr(>F)"]),
    stringsAsFactors = FALSE
  )
}))
write.csv(anova_rows, file.path(output_dir, "anova_results.csv"), row.names = FALSE)

writeLines(
  c(R.version.string, paste0("stats=", as.character(packageVersion("stats")))),
  file.path(output_dir, "r_version.txt"),
  useBytes = TRUE
)
