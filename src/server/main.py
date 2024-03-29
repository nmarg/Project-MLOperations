from csv import writer
from datetime import datetime
from http import HTTPStatus
from io import BytesIO

import pandas as pd
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from evidently.report import Report
from fastapi import BackgroundTasks, FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from google.cloud import storage
from PIL import Image
from transformers import ViTForImageClassification, ViTImageProcessor

from src.data.make_reference_data import calculate_image_params
from src.predict_model import predict

app = FastAPI()

BUCKET_NAME = "project-mloperations-data"

model_path = "models/model0"
model = ViTForImageClassification.from_pretrained(model_path)
model.eval()
processor = ViTImageProcessor.from_pretrained(model_path)


def upload_to_gcs(source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)


def download_from_gcs_to_dataframe(source_blob_name):
    """Downloads a blob from the bucket and loads it into a Pandas DataFrame."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(source_blob_name)
    data = blob.download_as_bytes()
    df = pd.read_csv(BytesIO(data))

    return df


def save_image_prediction(image, inference):
    image_params = calculate_image_params(image)
    csv_row = list(image_params)

    if inference == "Not attractive":
        inference = 0
    elif inference == "Attractive":
        inference = 1

    csv_row.append(inference)

    with open("data/drifting/current_data.csv", "a") as f_object:
        now = datetime.now()
        csv_row.append(now.strftime("%m/%d/%Y, %H:%M:%S"))
        writer_object = writer(f_object)
        writer_object.writerow(csv_row)

    upload_to_gcs("data/drifting/current_data.csv", "data/drifting/current_data.csv")


@app.post("/predict/")
async def server_predict(background_tasks: BackgroundTasks, data: UploadFile = File(...)):
    """
    USAGE:
        curl -X 'POST' \
            'http://localhost:8000/predict/' \
            -H 'accept: application/json' \
            -H 'Content-Type: multipart/form-data' \
            -F 'data=@/path/to/your/image.jpg;type=image/jpeg'
    """
    # read the data
    content = await data.read()
    image_stream = BytesIO(content)
    image_stream.seek(0)

    # Open the image using PIL
    image = Image.open(image_stream)
    image_tensor = processor(image, return_tensors="pt")

    # get the predicitons from the model
    inference = predict(model, image_tensor)
    response = {
        "inference": inference,
        "message": HTTPStatus.OK.phrase,
    }

    background_tasks.add_task(save_image_prediction, image, inference)

    return response


@app.get("/data-drifting-report", response_class=HTMLResponse)
def data_drifting_report():
    reference_data_file_name = "data/drifting/reference_data.csv"
    current_data_file_name = "data/drifting/current_data.csv"
    reference_data = download_from_gcs_to_dataframe(reference_data_file_name)
    current_data = download_from_gcs_to_dataframe(current_data_file_name)

    last_column_name = current_data.columns[-1]
    current_data = current_data.drop(last_column_name, axis=1)

    report = Report(metrics=[DataDriftPreset(), DataQualityPreset()])
    report.run(reference_data=reference_data, current_data=current_data)
    report.save_html("report.html")

    with open("report.html", "r") as file:
        html_content = file.read()

    return HTMLResponse(content=html_content, status_code=200)
