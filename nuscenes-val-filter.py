from nuscenes.nuscenes import NuScenes
import os

nusc = NuScenes(version='v1.0-trainval', dataroot='./datasets/nuscenes-trainval', verbose=True)

val_day = \
        ['scene-0003', 'scene-0012', 'scene-0013', 'scene-0014', 'scene-0015', 'scene-0016', 'scene-0017', 'scene-0018',
         'scene-0035', 'scene-0036',
         'scene-0038', 'scene-0039', 'scene-0092', 'scene-0093', 'scene-0094', 'scene-0095', 'scene-0096', 'scene-0097',
         'scene-0098', 'scene-0099',
         'scene-0100', 'scene-0101', 'scene-0102', 'scene-0103', 'scene-0104', 'scene-0105', 'scene-0106', 'scene-0107',
         'scene-0108', 'scene-0109',
         'scene-0110', 'scene-0221', 'scene-0268', 'scene-0269', 'scene-0270', 'scene-0271', 'scene-0272', 'scene-0273',
         'scene-0274', 'scene-0275',
         'scene-0276', 'scene-0277', 'scene-0278', 'scene-0329', 'scene-0330', 'scene-0331', 'scene-0332', 'scene-0344',
         'scene-0345', 'scene-0346',
         'scene-0519', 'scene-0520', 'scene-0521', 'scene-0522', 'scene-0523', 'scene-0524', 'scene-0552', 'scene-0553',
         'scene-0554', 'scene-0555',
         'scene-0556', 'scene-0557', 'scene-0558', 'scene-0559', 'scene-0560', 'scene-0561', 'scene-0562', 'scene-0563',
         'scene-0564', 'scene-0565',
         'scene-0770', 'scene-0771', 'scene-0775', 'scene-0777', 'scene-0778', 'scene-0780', 'scene-0781', 'scene-0782',
         'scene-0783', 'scene-0784',
         'scene-0794', 'scene-0795', 'scene-0796', 'scene-0797', 'scene-0798', 'scene-0799', 'scene-0800', 'scene-0802',
         'scene-0916', 'scene-0917',
         'scene-0919', 'scene-0920', 'scene-0921', 'scene-0922', 'scene-0923', 'scene-0924', 'scene-0925', 'scene-0926',
         'scene-0927', 'scene-0928',
         'scene-0929', 'scene-0930', 'scene-0931', 'scene-0962', 'scene-0963', 'scene-0966', 'scene-0967', 'scene-0968',
         'scene-0969', 'scene-0971',
         'scene-0972']

val_rain = \
         ['scene-0625', 'scene-0626', 'scene-0627', 'scene-0629', 'scene-0630', 'scene-0632', 'scene-0633',
          'scene-0634', 'scene-0635', 'scene-0636',
          'scene-0637', 'scene-0638', 'scene-0904', 'scene-0905', 'scene-0906', 'scene-0907', 'scene-0908',
          'scene-0909', 'scene-0910', 'scene-0911',
          'scene-0912', 'scene-0913', 'scene-0914', 'scene-0915']

val_night = \
          ['scene-1059', 'scene-1060', 'scene-1061', 'scene-1062', 'scene-1063', 'scene-1064', 'scene-1065',
           'scene-1066', 'scene-1067', 'scene-1068',
           'scene-1069', 'scene-1070', 'scene-1071', 'scene-1072', 'scene-1073']

val_scenes = val_day+ val_rain + val_night

def delete_file(filename):
    filepath = os.path.join(nusc.dataroot, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        #print(f"Deleted: {filepath}")
   # else:
        #print(f"File not found: {filepath}")

for scene in nusc.scene:
    if scene['name'] in val_scenes: # only filter out scenes in train data
        continue
    print(f"scene: {scene['name']}")
    first_sample_token = scene['first_sample_token']
    my_sample = nusc.get('sample', first_sample_token)
    while my_sample:

        for sensor in {'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT', 'CAM_BACK_RIGHT', 'CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT',
                    'LIDAR_TOP', 'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT', 'RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT'}:
            try:
                sensor_data = nusc.get('sample_data', my_sample['data'][sensor])
                # Delete main sample file (samples/)
                delete_file(sensor_data['filename'])

                # Delete sweep files linked via 'prev' (sweeps/)
                sweep_token = sensor_data['prev']
                while sweep_token:
                    sweep_data = nusc.get('sample_data', sweep_token)
                    delete_file(sweep_data['filename'])
                    sweep_token = sweep_data['prev']

            except KeyError:
                print(f"Sensor {sensor} not found in sample {my_sample['token']}")

            # try:
            #     sensor_data = nusc.get('sample_data', my_sample['data'][sensor])
            #     sample_filepath = os.path.join(nusc.dataroot, sensor_data['filename'])
            #     sweep_filepath = os.path.join(nusc.dataroot,'sweeps/'+ sensor_data['filename'][8:])

            #     if os.path.exists(sample_filepath):
            #         os.remove(sample_filepath)
            #     else:
            #         print(f"File not found: {sample_filepath}")

            #     if os.path.exists(sweep_filepath):
            #         os.remove(sweep_filepath)
            #     else: 
            #         print(f"File not found: {sweep_filepath}")
            # except KeyError:
            #     print(f"Sensor {sensor} not found in sample {my_sample['token']}")
        
        if my_sample['next'] == '':
            break
        my_sample = nusc.get('sample', my_sample['next'])
    print(f"deleted: {scene['name']}")