#!/bin/bash

# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval01_blobs_lidar.tgz -O trainval-01.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval02_blobs_lidar.tgz -O trainval-02.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval03_blobs_lidar.tgz -O trainval-03.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval04_blobs_lidar.tgz -O trainval-04.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval05_blobs_lidar.tgz -O trainval-05.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval06_blobs_lidar.tgz -O trainval-06.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval07_blobs_lidar.tgz -O trainval-07.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval08_blobs_lidar.tgz -O trainval-08.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval09_blobs_lidar.tgz -O trainval-09.tgz &> wget.log &
# wget https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-trainval10_blobs_lidar.tgz -O trainval-10.tgz &> wget.log &

# wait  # wait for all background jobs to finish

# tar -xvzf trainval-01.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-02.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-03.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-04.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-05.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-06.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-07.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-08.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-09.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &
# tar -xvzf trainval-10.tgz -C ./datasets/nuscenes-trainval/ > extract2.log 2>&1 &

# rm -rf trainval-01.tgz
# rm -rf trainval-02.tgz
# rm -rf trainval-03.tgz
# rm -rf trainval-04.tgz
# rm -rf trainval-05.tgz
# rm -rf trainval-06.tgz
# rm -rf trainval-07.tgz
# rm -rf trainval-08.tgz
# rm -rf trainval-09.tgz
# rm -rf trainval-10.tgz

wait