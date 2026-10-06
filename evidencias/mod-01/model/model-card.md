# Model Card — dog-cat-resnet18 1.0.0

## Propósito

Clasificar recortes de cajas COCO (un objeto por recorte) en dog o cat dentro del portal de anotación del Proyecto 3.

## Datos y trazabilidad

- Model version: 1.0.0 (independiente del dataset)
- Release P2: v0.1.1
- Manifest hash (split 70/20/10): sha256:178b28bddb1bef5c05975fc7150710658627e31af08a1a12d94b98f9e99cb2b2
- MLflow run_id: bb448230424146349a969253d30db43b
- Checkpoint: runs:/bb448230424146349a969253d30db43b/checkpoints/best.pt
- Checkpoint SHA256: 84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52
- Clases: {'dog': 0, 'cat': 1}

## Arquitectura y preprocesamiento

- {'name': 'resnet18', 'image_size': 128, 'hidden_layers': [128], 'dropout': 0.2, 'pretrained': True, 'trainable': 'layer4'}
- {'resize': 'square', 'image_size': 128, 'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225]}

## Métricas de test

- accuracy_top1: 0.9577464788732394
- f1_macro: 0.9548441806232775
- correct: 68.0
- total: 71.0
- precision_dog: 0.9347826086956522
- recall_dog: 1.0
- f1_dog: 0.9662921348314606
- support_dog: 43.0
- precision_cat: 1.0
- recall_cat: 0.8928571428571429
- f1_cat: 0.9433962264150945
- support_cat: 28.0

## Limitaciones

- Solo distingue dog y cat: cualquier otro objeto se asigna a una de las dos clases.
- Clasifica el recorte de una caja; no imágenes completas con varios objetos.
- Evaluado en el test congelado del release v0.1.1 (71 recortes); con pocas muestras por clase las métricas tienen incertidumbre alta.
- Clase más débil en test: cat, recall 0.8929 (25/28). Errores de test: cat→dog: 3.

## Pesos preentrenados

ResNet18_Weights.IMAGENET1K_V1 (ImageNet-1K, torchvision); entrenado: layer4 (último bloque residual) y la cabeza; el resto del backbone congelado.
