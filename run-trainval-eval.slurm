#!/bin/bash
#SBATCH --job-name=run-eval    # create a short name for your job
#SBATCH --nodes=1                # node count
#SBATCH --ntasks=1               # total number of tasks across all nodes
#SBATCH --cpus-per-task=4        # cpu-cores per task (>1 if multi-threaded tasks)
#SBATCH --gres=gpu:1             # number of gpus per node
#SBATCH --mem=40G                 # Request memory
#SBATCH --output=slurm-trainval-LOWLIGHT-test2.out
#SBATCH --constraint=a100
#SBATCH --time=01:00:00          # total run time limit (HH:MM:SS)
#SBATCH --mail-type=begin        # send email when job begins
#SBATCH --mail-type=end          # send email when job ends
#SBATCH --mail-user=el5267@princeton.edu

python eval.py --config './configs/eval/eval_cam_only.yaml'