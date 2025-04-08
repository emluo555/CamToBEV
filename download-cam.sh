#!/bin/bash

# wget https://motional-nuscenes.s3.amazonaws.com/public/v1.0/v1.0-trainval08_blobs.tgz -O trainval-08.tgz &> wget8.log &
# wget https://motional-nuscenes.s3.amazonaws.com/public/v1.0/v1.0-trainval09_blobs.tgz -O trainval-09.tgz &> wget9.log &
# wget https://motional-nuscenes.s3.amazonaws.com/public/v1.0/v1.0-trainval10_blobs.tgz -O trainval-10.tgz &> wget10.log &

# wait  
# echo "All downloads have completed successfully!"
# # only start once previous downloads are done

# tar -xvzf trainval-08.tgz -C ./datasets/nuscenes-trainval/ > extract8.log 2>&1 &
# wait
tar -xvzf trainval-09.tgz -C ./datasets/nuscenes-trainval/ > extract9.log 2>&1 &
wait
tar -xvzf trainval-10.tgz -C ./datasets/nuscenes-trainval/ > extract10.log 2>&1 &
wait

# only start once unzipping is done 
# rm -rf trainval-08.tgz
rm -rf trainval-09.tgz
rm -rf trainval-10.tgz

wait