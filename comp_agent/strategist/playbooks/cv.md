# Computer Vision Playbook

## Baseline Phase
1. **Pretrained model**: Start with ResNet50 or EfficientNet-B0
2. **Standard augmentation**: Random flip, rotation, color jitter
3. **Training**: AdamW, cosine annealing, 10-20 epochs

## Improve Phase
1. **Larger models**: EfficientNet-B4, ConvNeXt, ViT
2. **Advanced augmentation**: Mixup, CutMix, RandAugment
3. **Progressive resizing**: Train on small images first, fine-tune on large
4. **External data**: Check if allowed; use ImageNet21k pretrained

## Ensemble Phase
1. **Model diversity**: Different architectures (CNN + ViT)
2. **TTA**: Test-time augmentation (flip, multi-crop)
3. **Pseudo-labeling**: Use confident predictions on test set

## Polish Phase
1. **Learning rate finder**: Optimal LR for each model
2. **SWA**: Stochastic weight averaging for last epochs
3. **Threshold calibration**: For multi-label problems
