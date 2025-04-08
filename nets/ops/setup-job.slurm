#!/bin/bash
#SBATCH --job-name=setup-DETR    # create a short name for your job
#SBATCH --nodes=1                # node count
#SBATCH --ntasks=1               # total number of tasks across all nodes
#SBATCH --cpus-per-task=1        # cpu-cores per task (>1 if multi-threaded tasks)
#SBATCH --gres=gpu:1             # number of gpus per node
#SBATCH --mem=32G                 # Request memory
#SBATCH --constraint=a100
#SBATCH --time=00:10:00          # total run time limit (HH:MM:SS)
#SBATCH --mail-type=begin        # send email when job begins
#SBATCH --mail-type=end          # send email when job ends
#SBATCH --mail-user=el5267@princeton.edu

module purge

source /home/el5267/miniconda3/bin/activate bevcar
module load cudatoolkit/12.4
module load gcc-toolset/10
export CUDA_HOME=/usr/local/cuda-12.4

python setup.py build install
python test.py