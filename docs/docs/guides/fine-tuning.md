# Fine-tuning

For fine-tuning an LLM with `dstack`'s API, specify a model, dataset, training parameters,
and required compute resources. `dstack` takes care of everything else.

??? info "Prerequisites"
    To use the fine-tuning API, ensure you have the latest version:

    <div class="termy">

    ```shell
    $ pip install "dstack[all]==0.12.3rc2"
    ```

    </div>

## Create a client

First, you connect to `dstack`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

## Create a task

Then, you create a fine-tuning task, specifying the model and dataset, 
and various [training parameters](../../docs/reference/api/python/index.md#dstack.api.FineTuningTask).

```python
from dstack.api import FineTuningTask

task = FineTuningTask(
    model_name="NousResearch/Llama-2-13b-hf",
    dataset_name="peterschmidt85/samsum",
    env={
        "HUGGING_FACE_HUB_TOKEN": "...",
    },
    num_train_epochs=2
)
```

!!! info "Dataset format"
    For the SFT fine-tuning method, the dataset should contain a `"text"` column with completions following the prompt format
    of the corresponding model.
    Check the [peterschmidt85/samsum](https://huggingface.co/datasets/peterschmidt85/samsum) example. 

## Run the task

When running a task, you can configure resources, and many [other options](../../docs/reference/api/python/index.md#dstack.api.RunCollection.submit).

```python
from dstack.api import Resources, GPU

run = client.runs.submit(
    run_name="Llama-2-13b-samsum", # (Optional) If unset, its chosen randomly
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

!!! info "Fine-tuning methods"
    The API currently supports only SFT, with support for DPO and other methods coming soon.

When the training is done, `dstack` pushes the final model to the Hugging Face hub.

![](../../assets/images/dstack-finetuning-hf.png){ width=800 }

## Manage runs

You can use the instance of [`dstack.api.Client`](../../docs/reference/api/python/index.md#dstack.api.Client) to manage your runs, 
including getting a list of runs, stopping a given run, etc.

## Track experiments

To track experiment metrics, specify `report_to` and related authentication environment variables.

```python
task = FineTuningTask(
    model_name="NousResearch/Llama-2-13b-hf",
    dataset_name="peterschmidt85/samsum",
    report_to="wandb",
    env={
        "HUGGING_FACE_HUB_TOKEN": "...",
        "WANDB_API_KEY": "...",
    },
    num_train_epochs=2
)
```

Currently, the API supports `"tensorboard"` and `"wandb"`.

![](../../assets/images/dstack-finetuning-wandb.png){ width=800 }

[//]: # (TODO: Example)
[//]: # (TODO: Next steps)