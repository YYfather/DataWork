#!/usr/bin/env Rscript

# Development-only independent R reference for every runnable DataWork method.
# It intentionally lives under tests and is never imported by the application.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) stop("usage: validate_all_methods.R <repo-root> <manifest.json> <output.csv>")
root <- normalizePath(args[[1]], winslash = "/", mustWork = TRUE)
manifest_path <- normalizePath(args[[2]], winslash = "/", mustWork = TRUE)
output_path <- args[[3]]
local_lib <- file.path(root, ".r-validation-lib")
if (dir.exists(local_lib)) .libPaths(c(local_lib, .libPaths()))

required <- c("jsonlite", "car", "DescTools", "exact2x2", "nnet", "MASS", "nlme")
missing <- required[!vapply(required, requireNamespace, quietly = TRUE, FUN.VALUE = logical(1))]
if (length(missing)) stop("missing R validation packages: ", paste(missing, collapse = ", "))

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0) y else x
manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
rows <- list()
seen <- character()

emit <- function(case_id, method, statistic, p_value = NA_real_, df_num = NA_real_, df_den = NA_real_) {
  rows[[length(rows) + 1]] <<- data.frame(
    case_id = case_id, method = method,
    statistic = as.numeric(statistic), p_value = as.numeric(p_value),
    df_num = as.numeric(df_num), df_den = as.numeric(df_den),
    stringsAsFactors = FALSE
  )
}

split_names <- function(x) unlist(x %||% list(), use.names = FALSE)
factorize <- function(df, columns) {
  for (column in columns) df[[column]] <- factor(df[[column]])
  df
}
safe_number <- function(x) suppressWarnings(as.numeric(x))
first_factor <- function(plan) split_names(plan$fixed_factors)[[1]]
first_dv <- function(plan) split_names(plan$dependent_variables)[[1]]
formula_text <- function(lhs, factors, covariates = character(), interaction = TRUE) {
  rhs <- c(if (length(factors)) paste(factors, collapse = if (interaction) " * " else " + ") else character(), covariates)
  as.formula(paste(lhs, "~", paste(rhs, collapse = " + ")))
}

primary_anova <- function(df, plan, method) {
  dv <- first_dv(plan); factors <- split_names(plan$fixed_factors)
  covariates <- split_names(plan$covariates)
  df <- factorize(df, factors)
  contrasts_arg <- setNames(as.list(rep("contr.sum", length(factors))), factors)
  fit <- lm(formula_text(dv, factors, covariates, interaction = method != "ancova"), data = df,
            contrasts = contrasts_arg)
  table <- as.data.frame(car::Anova(fit, type = 3))
  effect <- factors[[1]]
  index <- which(trimws(rownames(table)) == effect)[[1]]
  pcol <- grep("Pr\\(>F\\)", names(table))[[1]]
  c(statistic = table[index, "F value"], p_value = table[index, pcol],
    df_num = table[index, "Df"], df_den = df.residual(fit))
}

primary_manova <- function(df, plan) {
  dvs <- split_names(plan$dependent_variables); factors <- split_names(plan$fixed_factors)
  df <- factorize(df, factors)
  lhs <- paste0("cbind(", paste(dvs, collapse = ","), ")")
  fit <- manova(formula_text(lhs, factors), data = df)
  table <- summary(fit, test = "Pillai")$stats
  row <- table[which(trimws(rownames(table)) == factors[[1]])[[1]], ]
  c(statistic = row[["Pillai"]], p_value = row[["Pr(>F)"]],
    df_num = row[["num Df"]], df_den = row[["den Df"]])
}

for (case in manifest$cases) {
  method <- case$method
  if (method == "factorial_anova" || method %in% seen) next
  seen <- c(seen, method)
  case_id <- case$case_id; plan <- case$plan
  path <- file.path(root, "golden_datasets", case$dataset)
  df <- read.csv(path, check.names = FALSE, stringsAsFactors = FALSE)
  dvs <- split_names(plan$dependent_variables); factors <- split_names(plan$fixed_factors)
  covariates <- split_names(plan$covariates)

  if (method == "descriptive_statistics") {
    emit(case_id, method, mean(df[[dvs[[1]]]], na.rm = TRUE))
  } else if (method == "one_sample_ttest") {
    out <- t.test(df[[dvs[[1]]]], mu = plan$test_value %||% 0)
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method %in% c("welch_ttest", "independent_ttest")) {
    values <- split(df[[dvs[[1]]]], df[[factors[[1]]]])
    out <- t.test(values[[1]], values[[2]], var.equal = method == "independent_ttest")
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "paired_ttest") {
    out <- t.test(df[[dvs[[1]]]], df[[dvs[[2]]]], paired = TRUE)
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "mann_whitney_u") {
    values <- split(df[[dvs[[1]]]], df[[factors[[1]]]])
    out <- wilcox.test(values[[1]], values[[2]], exact = TRUE, correct = FALSE)
    emit(case_id, method, unname(out$statistic), out$p.value)
  } else if (method == "wilcoxon_signed_rank") {
    out <- wilcox.test(df[[dvs[[1]]]], df[[dvs[[2]]]], paired = TRUE, exact = TRUE, correct = FALSE)
    emit(case_id, method, out$statistic, out$p.value)
  } else if (method %in% c("oneway_anova", "twoway_anova", "threeway_anova", "ancova", "multifactor_anova")) {
    out <- primary_anova(df, plan, method)
    emit(case_id, method, out[["statistic"]], out[["p_value"]], out[["df_num"]], out[["df_den"]])
  } else if (method == "welch_anova") {
    out <- oneway.test(df[[dvs[[1]]]] ~ factor(df[[factors[[1]]]]), var.equal = FALSE)
    emit(case_id, method, out$statistic, out$p.value, out$parameter[[1]], out$parameter[[2]])
  } else if (method == "kruskal_wallis") {
    out <- kruskal.test(df[[dvs[[1]]]] ~ factor(df[[factors[[1]]]]))
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method %in% c("pearson_correlation", "spearman_correlation", "kendall_correlation")) {
    kind <- sub("_correlation", "", method)
    out <- suppressWarnings(cor.test(df[[dvs[[1]]]], df[[dvs[[2]]]], method = kind, exact = FALSE))
    emit(case_id, method, out$estimate, out$p.value)
  } else if (method == "linear_regression") {
    df <- factorize(df, factors)
    fit <- lm(formula_text(dvs[[1]], factors, covariates, interaction = FALSE), data = df)
    s <- summary(fit); f <- s$fstatistic
    emit(case_id, method, unname(f[[1]]), pf(f[[1]], f[[2]], f[[3]], lower.tail = FALSE), f[[2]], f[[3]])
  } else if (method == "logistic_regression") {
    df <- factorize(df, factors); success <- as.character(plan$method_parameters$success_level %||% "1")
    df[[dvs[[1]]]] <- as.integer(as.character(df[[dvs[[1]]]]) == success)
    full <- glm(formula_text(dvs[[1]], factors, covariates, interaction = FALSE), data = df, family = binomial())
    null <- glm(as.formula(paste(dvs[[1]], "~ 1")), data = df, family = binomial())
    lr <- 2 * (as.numeric(logLik(full)) - as.numeric(logLik(null))); dfd <- attr(logLik(full), "df") - attr(logLik(null), "df")
    emit(case_id, method, lr, pchisq(lr, dfd, lower.tail = FALSE), dfd)
  } else if (method == "chi_square_independence") {
    out <- suppressWarnings(chisq.test(table(df[[factors[[1]]]], df[[factors[[2]]]]), correct = TRUE))
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "fisher_exact") {
    tab <- table(df[[factors[[1]]]], df[[factors[[2]]]]); out <- fisher.test(tab)
    sample_or <- unname(tab[1, 1] * tab[2, 2] / (tab[1, 2] * tab[2, 1]))
    emit(case_id, method, sample_or, out$p.value)
  } else if (method == "chi_square_goodness_of_fit") {
    counts <- table(df[[factors[[1]]]]); probs <- unlist(plan$expected_proportions %||% rep(1 / length(counts), length(counts)))
    out <- chisq.test(counts, p = probs)
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "mcnemar_test") {
    tab <- table(df[[dvs[[1]]]], df[[dvs[[2]]]]); b <- tab[1, 2]; c <- tab[2, 1]
    out <- binom.test(min(b, c), b + c, p = 0.5)
    emit(case_id, method, min(b, c), out$p.value)
  } else if (method == "exact_binomial_test") {
    level <- as.character(plan$method_parameters$success_level); hit <- sum(as.character(df[[factors[[1]]]]) == level); n <- nrow(df)
    out <- binom.test(hit, n, p = 0.5)
    emit(case_id, method, hit / n, out$p.value)
  } else if (method == "one_sample_proportion_ztest") {
    level <- as.character(plan$method_parameters$success_level); hit <- sum(as.character(df[[factors[[1]]]]) == level); n <- nrow(df); phat <- hit / n
    z <- (phat - 0.5) / sqrt(phat * (1 - phat) / n)
    emit(case_id, method, z, 2 * pnorm(abs(z), lower.tail = FALSE))
  } else if (method == "two_proportion_ztest") {
    level <- as.character(plan$method_parameters$success_level); g <- split(df, df[[factors[[1]]]])
    x <- vapply(g, function(v) sum(as.character(v[[dvs[[1]]]]) == level), numeric(1)); n <- vapply(g, nrow, numeric(1)); p <- x / n; pooled <- sum(x) / sum(n)
    z <- (p[[1]] - p[[2]]) / sqrt(pooled * (1 - pooled) * sum(1 / n))
    emit(case_id, method, z, 2 * pnorm(abs(z), lower.tail = FALSE))
  } else if (method == "k_proportion_chi_square") {
    tab <- table(df[[factors[[1]]]], df[[dvs[[1]]]]); out <- prop.test(tab, correct = FALSE)
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "barnard_exact") {
    tab <- table(df[[factors[[1]]]], df[[factors[[2]]]]); out <- DescTools::BarnardTest(tab, method = "z-pooled")
    emit(case_id, method, unname(out$statistic), out$p.value)
  } else if (method == "boschloo_exact") {
    tab <- table(df[[factors[[1]]]], df[[factors[[2]]]])
    out <- exact2x2::boschloo(tab[1, 1], sum(tab[1, ]), tab[2, 1], sum(tab[2, ]))
    fisher_statistic <- fisher.test(tab, alternative = "less")$p.value
    emit(case_id, method, fisher_statistic, out$p.value)
  } else if (method == "cochran_q_test") {
    out <- DescTools::CochranQTest(as.matrix(df[, dvs]))
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "bowker_symmetry") {
    tab <- table(df[[dvs[[1]]]], df[[dvs[[2]]]]); stat <- 0; dfd <- 0
    for (i in seq_len(nrow(tab) - 1)) for (j in (i + 1):ncol(tab)) if (tab[i, j] + tab[j, i] > 0) {
      stat <- stat + (tab[i, j] - tab[j, i])^2 / (tab[i, j] + tab[j, i]); dfd <- dfd + 1
    }
    emit(case_id, method, stat, pchisq(stat, dfd, lower.tail = FALSE), dfd)
  } else if (method == "stuart_maxwell") {
    out <- DescTools::StuartMaxwellTest(table(df[[dvs[[1]]]], df[[dvs[[2]]]]))
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method %in% c("cochran_mantel_haenszel", "breslow_day")) {
    outcome <- dvs[[1]]; exposure <- factors[[1]]; strata <- factors[[2]]
    tab <- xtabs(as.formula(paste("~", exposure, "+", outcome, "+", strata)), data = df)
    if (method == "cochran_mantel_haenszel") out <- mantelhaen.test(tab, correct = FALSE) else out <- DescTools::BreslowDayTest(tab, OR = NA)
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "cohen_kappa") {
    tab <- table(df[[dvs[[1]]]], df[[dvs[[2]]]]); n <- sum(tab); po <- sum(diag(tab)) / n; pe <- sum(rowSums(tab) * colSums(tab)) / n^2
    emit(case_id, method, (po - pe) / (1 - pe))
  } else if (method == "fleiss_kappa") {
    ratings <- as.matrix(df[, dvs]); levels <- sort(unique(as.vector(ratings))); counts <- t(apply(ratings, 1, function(x) table(factor(x, levels = levels))))
    raters <- ncol(ratings); p_i <- (rowSums(counts^2) - raters) / (raters * (raters - 1)); p_j <- colSums(counts) / (nrow(ratings) * raters)
    emit(case_id, method, (mean(p_i) - sum(p_j^2)) / (1 - sum(p_j^2)))
  } else if (method == "cochran_armitage_trend") {
    outcome <- dvs[[1]]; dose <- factors[[1]]; success <- as.character(plan$method_parameters$success_level); order <- strsplit(plan$method_parameters$level_order, ",")[[1]]; scores <- safe_number(strsplit(plan$method_parameters$scores, ",")[[1]])
    n <- vapply(order, function(level) sum(df[[dose]] == level), numeric(1)); x <- vapply(order, function(level) sum(df[[dose]] == level & as.character(df[[outcome]]) == success), numeric(1)); phat <- sum(x) / sum(n)
    z <- sum(scores * (x - n * phat)) / sqrt(phat * (1 - phat) * (sum(n * scores^2) - sum(n * scores)^2 / sum(n)))
    emit(case_id, method, z, 2 * pnorm(abs(z), lower.tail = FALSE))
  } else if (method == "multinomial_logistic_regression") {
    df <- factorize(df, factors); df[[dvs[[1]]]] <- factor(df[[dvs[[1]]]])
    full <- nnet::multinom(formula_text(dvs[[1]], factors, covariates, interaction = FALSE), data = df, trace = FALSE)
    null <- nnet::multinom(as.formula(paste(dvs[[1]], "~ 1")), data = df, trace = FALSE)
    lr <- 2 * (as.numeric(logLik(full)) - as.numeric(logLik(null))); dfd <- attr(logLik(full), "df") - attr(logLik(null), "df")
    emit(case_id, method, lr, pchisq(lr, dfd, lower.tail = FALSE), dfd)
  } else if (method == "ordinal_logistic_regression") {
    order <- strsplit(plan$method_parameters$level_order, ",")[[1]]; df <- factorize(df, factors); df[[dvs[[1]]]] <- ordered(df[[dvs[[1]]]], levels = order)
    full <- MASS::polr(formula_text(dvs[[1]], factors, covariates, interaction = FALSE), data = df, method = "logistic", Hess = TRUE)
    null <- MASS::polr(as.formula(paste(dvs[[1]], "~ 1")), data = df, method = "logistic", Hess = TRUE)
    lr <- 2 * (as.numeric(logLik(full)) - as.numeric(logLik(null))); dfd <- attr(logLik(full), "df") - attr(logLik(null), "df")
    emit(case_id, method, lr, pchisq(lr, dfd, lower.tail = FALSE), dfd)
  } else if (method == "repeated_measures_anova") {
    subject <- plan$subject_id; time <- plan$repeated_factor; dv <- dvs[[1]]
    subject_means <- ave(df[[dv]], df[[subject]], FUN = mean); grand <- mean(df[[dv]]); time_means <- tapply(df[[dv]], df[[time]], mean); subject_avg <- tapply(df[[dv]], df[[subject]], mean)
    n_subject <- length(subject_avg); k <- length(time_means); ss_time <- n_subject * sum((time_means - grand)^2); ss_subject <- k * sum((subject_avg - grand)^2); ss_total <- sum((df[[dv]] - grand)^2); ss_error <- ss_total - ss_time - ss_subject
    df1 <- k - 1; df2 <- (n_subject - 1) * (k - 1); f <- (ss_time / df1) / (ss_error / df2)
    emit(case_id, method, f, pf(f, df1, df2, lower.tail = FALSE), df1, df2)
  } else if (method == "friedman_test") {
    out <- friedman.test(df[[dvs[[1]]]], factor(df[[plan$repeated_factor]]), factor(df[[plan$subject_id]]))
    emit(case_id, method, out$statistic, out$p.value, out$parameter)
  } else if (method == "linear_mixed_model") {
    df <- factorize(df, c(factors, split_names(plan$random_factors))); cluster <- split_names(plan$random_factors)[[1]]
    fit <- nlme::lme(formula_text(dvs[[1]], factors, covariates, interaction = FALSE), random = as.formula(paste("~1|", cluster)), data = df, method = "ML")
    emit(case_id, method, nlme::fixef(fit)[[covariates[[1]]]])
  } else if (method %in% c("oneway_manova", "twoway_manova", "threeway_manova", "multifactor_manova")) {
    out <- primary_manova(df, plan)
    emit(case_id, method, out[["statistic"]], out[["p_value"]], out[["df_num"]], out[["df_den"]])
  } else if (method == "mixed_anova") {
    subject <- plan$subject_id; group <- factors[[1]]; dv <- dvs[[1]]
    means <- aggregate(df[[dv]], list(subject = df[[subject]], group = df[[group]]), mean); fit <- aov(x ~ factor(group), data = means); table <- summary(fit)[[1]]
    emit(case_id, method, table[1, "F value"], table[1, "Pr(>F)"], table[1, "Df"], table[2, "Df"])
  } else stop("unhandled method: ", method)
}

result <- do.call(rbind, rows)
write.csv(result, output_path, row.names = FALSE, na = "")
cat(R.version.string, "\n")
cat("validated methods:", nrow(result), "\n")
