# Dataset extraction
## Pipeline
<p align="center" width="100%">
    <img width="25%" src="../figs/data_preprocessing.jpg"> 
</p>

## Data directory
Prepare data directory as:
```
|- AIC_Video 
   |- Videos_L01
   |- Videos_L02
   |- ...

```

## Usage
- *Chạy theo thứ tự bên dưới*
- Audio extraction: [audio](audio/README.md)
- Metadata extraction: [metadata](metadata/README.md)
- Clip features extraction:: [clip](clip/README.md)
- Run [create.ipynb](./create.ipynb) for bin generation
- Run [fps.ipynb](./fps.ipynb) for fps.json generation
- Run [SceneJSON.ipynb](./SceneJSON.ipynb) for SceneJSON.json generation
- Run [data_preparation.ipynb](./data_preparation.ipynb)