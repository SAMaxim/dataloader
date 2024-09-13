from rich_argparse import RichHelpFormatter
from rich.prompt import Confirm, Prompt
from datetime import datetime
from rich.panel import Panel
from rich import print
import subprocess
import argparse
import pathlib
import zipfile
import string
import random
import shutil
import click
import boto3
import json
import tqdm
import os

def upload_to_s3(bucket, path_local, path_s3):
    # checking that s3 path correct (don't start with /)
    if path_s3.startswith("/"):
        path_s3 = path_s3[1:]
    session = boto3.session.Session()
    s3_client = session.client(
        service_name="s3",
        endpoint_url="https://obs.ru-moscow-1.hc.sbercloud.ru",
        region_name="ru-1a",
    )
    # Get the size of the file
    file_size = os.path.getsize(
        path_local
    )  # Callback function to update the tqdm progress bar

    def tqdm_callback(bytes_transferred):
        progress_bar.update(bytes_transferred)

    with tqdm.tqdm(
        total=file_size, unit="B", unit_scale=True, desc="Uploading"
    ) as progress_bar:
        s3_client.upload_file(
            Filename=path_local,
            Bucket=bucket,
            Key=path_s3,
            ExtraArgs={"ACL": "authenticated-read"},
            Callback=tqdm_callback,
        )

cam_to_sd_serials_correspondence = {}

def generate_random_name():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8)) + ".MP4"

def is_writable(path):
    if os.access(path, os.W_OK) is not True:
        return False

    else:
        return True

def get_metadata_with_large_file_support(file_path):
    try:
        result = subprocess.run(
            ["exiftool", "-api", "LargeFileSupport=1", "-json", file_path],
            capture_output=True,
            text=True,
        )
        metadata = json.loads(result.stdout)
        return metadata[0] if metadata else None
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_sd_card_serial():
    try:
        cmd = ["udevadm", "info", "-a", "-n", "/dev/mmcblk0"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout
        grep_result = [line for line in output.splitlines() if "serial" in line]
        serial_number = grep_result[0].split("==")[1].strip('"')
    except Exception as e:
        serial_number = "None"
    return serial_number

def get_camera_serial(sd_card_video_path):
    mp4_video_path = [
        os.path.join(sd_card_video_path, file)
        for file in os.listdir(sd_card_video_path)
        if file.endswith(".MP4") or file.endswith(".mp4")
    ][0]
    metadata = get_metadata_with_large_file_support(mp4_video_path)
    return metadata["CameraSerialNumber"]

def get_sd_card_video_path():
    username = os.getlogin()

    while (len(os.listdir(f"/media/{username}"))) == 0:
        Prompt.ask("NO SD CARD FOUND! INSERT AND PRESS ENTER")
    device = [
        file
        for file in os.listdir(f"/media/{username}")
        if not file.startswith("Windows")
    ][0]
    # if device == "Windows":
    #     device = os.listdir(f"/media/{username}")[1]
    right_folders = [x for x in os.listdir(os.path.join(f"/media/{username}", device, "DCIM")) if x.endswith('GOPRO')]
    sd_card_video_pathes =  [os.path.join(f"/media/{username}", device, "DCIM", x) for x in right_folders]
    return sd_card_video_pathes

def move_files_from_SD_card_to_local_storage(target_dir):
    global cam_to_sd_serials_correspondence
    Prompt.ask("Insert SD card and press Enter")
    while True:
        sd_card_video_pathes = get_sd_card_video_path()
        if not is_writable(sd_card_video_pathes[0]):
            Prompt.ask(
                "SD card not writeable, turn off write protection, reinsert this and press Enter"
            )
        else:
            break

    all_files =  []
    for sd_card_video_path in sd_card_video_pathes:
        all_files.extend(os.listdir(sd_card_video_path))
    all_files = [x for x in all_files if x.endswith(".MP4") or x.endswith(".mp4")]
    print(f"FOUND {len(all_files)} MP4 files on SD card")
    if (len(all_files)) == 0:
        print("YOU INSERTED EMPTY CARD, SKIPPING")
        return

    for sd_card_video_path in sd_card_video_pathes:
        files = [
            file
            for file in os.listdir(sd_card_video_path)
            if file.endswith(".MP4") or file.endswith(".mp4")
        ]
        if len(files) == 0:
            continue

        # Moving files
        cam_serial = get_camera_serial(sd_card_video_path)
        sd_serial = get_sd_card_serial()
        cam_to_sd_serials_correspondence[cam_serial] = sd_serial

        for file in tqdm.tqdm(files, desc="Moving files to local storage"):
            if os.path.exists(os.path.join(target_dir, file)):
                shutil.move(
                    os.path.join(sd_card_video_path, file),
                    os.path.join(target_dir, generate_random_name()),
                )
            else:
                shutil.move(os.path.join(sd_card_video_path, file), target_dir)

        print(f"Cleaning SD card...{sd_card_video_path}")
        for file in os.listdir(sd_card_video_path):
            os.remove(os.path.join(sd_card_video_path, file))

def pack_and_upload():
    local_storage_folder = os.path.join(os.path.expanduser("~"), "umi_raw_data")
    current_date = datetime.now().strftime("%d.%m.%Y")

    # getting task description
    task = None
    while task is None:
        task = Prompt.ask("[green]Enter task description[/green]")
        if len(task) == 0:
            print("Task description cannot be empty, enter it again")
            task = None
            continue
        task = task.lower().replace(" ", "_")
        is_task_correct = Confirm.ask(
            f"Is task description correct?: [red]{task}[/red]"
        )
        if not is_task_correct:
            task = None
            continue
    task_folder_name = f"{task}.{current_date}"
    print(f"Task folder name: {task_folder_name}")
    task_folder_path = new_folder_path = os.path.join(
        local_storage_folder, task_folder_name
    )
    print(f"Global task folder path is {task_folder_path}")
    if os.path.exists(task_folder_path):

        amount_of_mp4_videos = 0
        try:
            amount_of_mp4_videos = len(
                [
                    file
                    for file in os.listdir(
                        os.path.joint(task_folder_path, "raw_videos")
                    )
                    if file.endswith(".MP4") or file.endswith(".mp4")
                ]
            )
        except:
            pass
        is_overwrite = Confirm.ask(
            f"Folder already exists with {amount_of_mp4_videos}, do you want to overwrite it?"
        )
        if is_overwrite:
            shutil.rmtree(task_folder_path)
            os.mkdir(task_folder_path)
    raw_videos_folder = os.path.join(new_folder_path, "raw_videos")
    os.makedirs(raw_videos_folder, exist_ok=True)

    while True:
        is_add_files_from_sd = Confirm.ask(
            "Would you like to move files from SD card to local storage?"
        )

        if not is_add_files_from_sd:
            break

        move_files_from_SD_card_to_local_storage(raw_videos_folder)
    json.dump(
        cam_to_sd_serials_correspondence,
        open(f"{new_folder_path}/cam_sd_serial.json", "w"),
    )
    print("Creating and uploading ZIP file")
    # Zip the folder
    amount_of_episodes = len(os.listdir(raw_videos_folder))

    zip_file_name = f"{task_folder_name}.{amount_of_episodes}_episodes.zip"
    zip_file_path = os.path.join(new_folder_path, zip_file_name)
    with zipfile.ZipFile(zip_file_path, "w") as zipf:
        for root, dirs, files in os.walk(new_folder_path):
            if len(files) > 2:
                for file in tqdm.tqdm(files, desc="Zipping videos"):
                    zipf.write(
                        os.path.join(root, file),
                        os.path.relpath(os.path.join(root, file), new_folder_path),
                    )
            else:
                for file in files:
                    zipf.write(
                        os.path.join(root, file),
                        os.path.relpath(os.path.join(root, file), new_folder_path),
                    )
    # Upload zip file to S3

    s3_zip_path = f"datasets/umi/raw_data/test/{zip_file_name}"
    upload_to_s3("umi-external", zip_file_path, s3_zip_path)

    print(
        f"Folder packed and uploaded successfully as {zip_file_name} to S3: {s3_zip_path}"
    )

def main():
    pack_and_upload()
    pass

if __name__ == "__main__":
    main()
