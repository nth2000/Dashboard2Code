# Dashboard2Code: Evaluating Multimodal Models on Reconstructing Interactive Dashboards

<img width="497" height="480" alt="图片" src="https://github.com/user-attachments/assets/caf33042-2cc7-4694-b433-337ba31b8317" />

Automatic data visualization generation have advanced rapidly with multi-modal large language models, yet existing efforts largely focus on static charts and overlook the interactive dashboards commonly used for real-world data exploration. We introduce Dashboard2Code, a novel task that requires a model to proactively explore an interactive dashboard, acquire and integrate feedback from its own interactions (e.g., clicking and filtering), and generate code that reproduces the target dashboard.



## Setup
```
conda create -n dashboard2code python=3.10
conda activate dashboard2code
pip install -r requirements.txt
```

For modules 'call_llm/call_{model}', modify call_llm/call_llm_template.py to implement the call logic.

## Usage
### View the dashboards
```
python dashboard_server.py
```

### Code Generation
Configure the parameters in batch_generate.py, then run the script.
```
python batch_generate.py
```
Then check the generated_outputs in generated_outputs/run_{date}_{time}/{output_file}
If generated successfully, rename generated_outputs/run_{date}_{time} to the name of output_file for evaluation steps.
### Evaluation
Evaluation process consists of several steps.
1. run batch_semantic_eval.py to precalculate semantic evaluation results.
2. run task_executor.py to execute the annotated tasks.
3. run batch_image_eval.py to precalculate image evaluation results.
Steps above are merged in run_evals.py.
```
cd evaluation
python run_evals.py
```
4. run generate_experiment_report.py to generate the final evaluation results.
```
python generate_experiment_report.py
```

## Results
<img width="852" height="362" alt="图片" src="https://github.com/user-attachments/assets/9cedbf3b-aa0c-40f1-8d52-a28ecb3a1ff3" />


## Contact info
If you have any questions or issues, feel free to contact thniu@ir.hit.edu.cn 
