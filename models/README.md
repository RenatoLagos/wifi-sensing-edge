# models/

Trained model artifacts and exports.

## Subdirs (gitignored content)

```
checkpoints/  PyTorch .pth checkpoints from training (gitignored)
exports/      Frozen ONNX exports + TensorRT engines (gitignored)
```

## What we track in git

- Architecture definitions live in `jetson/inference/`, not here
- Training scripts live in `notebooks/` or `scripts/`
- Hyperparameter configs (small YAML) can live here

## What we do NOT commit

- `.pth`, `.pt`, `.onnx`, `.engine`, `.trt`, `.plan` — too large, regeneratable
- Raw datasets — those live in `data/`
