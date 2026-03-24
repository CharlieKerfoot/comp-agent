# NLP Playbook

## Baseline Phase
1. **Pretrained transformer**: Start with DeBERTa-v3-base
2. **Simple fine-tuning**: Standard classification head, 3-5 epochs
3. **Tokenization**: Check max length, handle truncation

## Improve Phase
1. **Larger models**: DeBERTa-v3-large, RoBERTa-large
2. **Data augmentation**: Back-translation, synonym replacement
3. **Multi-task learning**: If auxiliary objectives available
4. **Prompt engineering**: For generative approaches

## Ensemble Phase
1. **Model diversity**: DeBERTa + RoBERTa + ELECTRA
2. **Different seeds**: Same model, different random seeds
3. **Fold averaging**: Cross-validation fold models

## Polish Phase
1. **Learning rate schedule**: Warm-up + linear decay
2. **Layer-wise LR decay**: Lower LR for earlier layers
3. **Post-processing**: Rule-based corrections for common patterns
