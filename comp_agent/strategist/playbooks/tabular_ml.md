# Tabular ML Playbook

## Baseline Phase
1. **EDA first**: Check distributions, missing values, cardinality, target balance
2. **Simple baseline**: XGBoost with default params + 5-fold CV
3. **Validation strategy**: Match competition's evaluation (stratified for classification)

## Improve Phase
1. **Feature engineering priorities**:
   - Frequency encoding for categoricals
   - Target encoding (use out-of-fold to avoid leakage)
   - Rolling statistics for time-based features
   - Interaction features between top predictors
2. **Model alternatives**: LightGBM (faster), CatBoost (handles categoricals natively)
3. **Missing value strategies**: Try both imputation and indicator features
4. **Feature selection**: Remove features with < 0.01 importance

## Ensemble Phase
1. **Diverse models**: Combine GBM + NN + linear model
2. **Stacking**: Out-of-fold predictions as meta-features
3. **Blending**: Optimize weights on validation set

## Polish Phase
1. **Hyperparameter tuning**: Optuna with 100+ trials
2. **Threshold tuning**: For classification, optimize threshold on validation
3. **Post-processing**: Round predictions, clip to valid range
