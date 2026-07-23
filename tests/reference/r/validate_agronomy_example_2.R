# DataWork 开发期独立 R 参考。
#
# 输入数据 tests/reference/r/agronomy_example_2.csv 的有效前 7 列与用户提供的
# 农业测试数据一致。脚本只使用 R 自带 stats，独立复核：
# - CK/T 按年份、品种、种植模式和组内原始顺序一一配对；
# - NDR 与 Delta 派生值；
# - 按年份执行的 Type III 双因素 ANOVA；
# - Wilks' Lambda 双因素 MANOVA。
#
# Python 对照入口：scripts/compare_r_reference.py
# Python 应用服务回归：tests/integration/test_agronomy_reference_dataset.py
# R 只用于开发期双重校对，不进入正式应用或服务器运行依赖。

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("用法: Rscript validate_agronomy_example_2.R <csv> <output_dir>")

source_path <- args[[1]]
output_dir <- args[[2]]
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

old_contrasts <- options(contrasts = c("contr.sum", "contr.poly"))
on.exit(options(old_contrasts), add = TRUE)

raw <- read.csv(
  source_path, header = TRUE, stringsAsFactors = FALSE,
  check.names = FALSE, fileEncoding = "UTF-8"
)
if (ncol(raw) < 7) stop("测试数据至少需要 7 列")
raw <- raw[, 1:7]
names(raw) <- c("year", "variety", "spray", "mode", "DR7", "DR14", "DR21")

pct_to_num <- function(x) as.numeric(sub("%", "", as.character(x), fixed = TRUE)) / 100
for (column in c("DR7", "DR14", "DR21")) raw[[column]] <- pct_to_num(raw[[column]])
raw$year <- trimws(as.character(raw$year))
raw$variety <- trimws(as.character(raw$variety))
raw$spray <- trimws(as.character(raw$spray))
raw$mode <- trimws(as.character(raw$mode))
raw <- raw[complete.cases(raw[, c("DR7", "DR14", "DR21")]), ]

ck <- raw[grepl("^CK", raw$spray), ]
trt <- raw[grepl("^T", raw$spray), ]
if (!nrow(ck) || !nrow(trt)) stop("缺少 CK 或 T 数据")

group_sequence <- function(df) {
  key <- interaction(df$year, df$variety, df$mode, df$spray, drop = TRUE)
  ave(seq_len(nrow(df)), key, FUN = seq_along)
}
ck$rep_id <- group_sequence(ck)
trt$rep_id <- group_sequence(trt)
trt$ck_id <- sub("^T", "CK", trt$spray)
ck$ck_id <- ck$spray

ck_keep <- ck[, c("year", "variety", "mode", "ck_id", "rep_id", "DR7", "DR14", "DR21")]
names(ck_keep)[6:8] <- c("CK_DR7", "CK_DR14", "CK_DR21")
merged <- merge(
  trt, ck_keep,
  by = c("year", "variety", "mode", "ck_id", "rep_id"),
  sort = FALSE
)
if (nrow(merged) != nrow(trt)) stop("CK/T 配对不完整")

for (day in c("7", "14", "21")) {
  merged[[paste0("NDR", day)]] <- round(merged[[paste0("CK_DR", day)]], 8)
  merged[[paste0("Delta", day)]] <- round(merged[[paste0("DR", day)]] - merged[[paste0("CK_DR", day)]], 8)
}

derived_columns <- c(
  "year", "variety", "spray", "mode", "rep_id",
  "NDR7", "Delta7", "NDR14", "Delta14", "NDR21", "Delta21"
)
derived <- merged[, derived_columns]
derived <- derived[order(derived$year, derived$variety, derived$spray, derived$mode, derived$rep_id), ]
write.csv(derived, file.path(output_dir, "agronomy_derived.csv"), row.names = FALSE, na = "")

type3_table <- function(fit) {
  matrix_full <- model.matrix(fit)
  response <- model.response(model.frame(fit))
  assignments <- attr(matrix_full, "assign")
  terms <- attr(terms(fit), "term.labels")
  rss_full <- sum(residuals(fit)^2)
  rank_full <- fit$rank
  df_den <- df.residual(fit)
  ms_error <- rss_full / df_den
  rows <- vector("list", length(terms))
  for (index in seq_along(terms)) {
    reduced <- lm.fit(matrix_full[, assignments != index, drop = FALSE], response)
    df_num <- rank_full - reduced$rank
    sum_sq <- sum(reduced$residuals^2) - rss_full
    f_value <- (sum_sq / df_num) / ms_error
    rows[[index]] <- data.frame(
      effect = terms[[index]], df_num = df_num, df_den = df_den,
      f_value = f_value, p_value = pf(f_value, df_num, df_den, lower.tail = FALSE),
      stringsAsFactors = FALSE
    )
  }
  do.call(rbind, rows)
}

anova_rows <- list()
manova_rows <- list()
for (year_value in sort(unique(merged$year))) {
  current <- merged[merged$year == year_value, ]
  current$variety <- factor(current$variety)
  current$spray <- factor(current$spray)
  for (day in c("7", "14", "21")) {
    outcomes <- c(paste0("NDR", day), paste0("Delta", day))
    for (outcome in outcomes) {
      fit <- lm(reformulate("variety * spray", response = outcome), data = current)
      table <- type3_table(fit)
      table$year <- year_value
      table$day <- paste0(day, "d")
      table$outcome <- outcome
      anova_rows[[length(anova_rows) + 1]] <- table[, c("year", "day", "outcome", "effect", "df_num", "df_den", "f_value", "p_value")]
    }

    formula <- as.formula(paste0("cbind(", outcomes[[1]], ", ", outcomes[[2]], ") ~ variety * spray"))
    fit_m <- manova(formula, data = current)
    stats <- summary(fit_m, test = "Wilks")$stats
    for (effect in c("variety", "spray", "variety:spray")) {
      row <- stats[effect, ]
      manova_rows[[length(manova_rows) + 1]] <- data.frame(
        year = year_value, day = paste0(day, "d"), effect = effect,
        statistic_value = unname(row[["Wilks"]]),
        df_num = unname(row[["num Df"]]), df_den = unname(row[["den Df"]]),
        f_value = unname(row[["approx F"]]), p_value = unname(row[["Pr(>F)"]]),
        stringsAsFactors = FALSE
      )
    }
  }
}

write.csv(do.call(rbind, anova_rows), file.path(output_dir, "agronomy_anova.csv"), row.names = FALSE)
write.csv(do.call(rbind, manova_rows), file.path(output_dir, "agronomy_manova.csv"), row.names = FALSE)
writeLines(c(R.version.string, paste0("stats=", as.character(packageVersion("stats")))), file.path(output_dir, "r_version.txt"))
