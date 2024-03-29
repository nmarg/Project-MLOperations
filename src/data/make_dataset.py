import math
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from transformers import TensorType, ViTImageProcessor

MAX_DATASET_LENGTH = 202599
PROCESSED_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data/processed/"
TESTING_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data/testing/"
TRAINING_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data/training/"
RAW_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data/raw/"
LIGHT_WEIGHT_AMOUNT = 5


class CustomImageDataset(Dataset):
    def __init__(
        self,
        images: np.ndarray,
        labels: np.ndarray,
        light_weight=False,
        light_weight_amount=LIGHT_WEIGHT_AMOUNT,
    ):
        """Custom dataset that loads images and labels, then returns them on demand into a DataLoader.
        Outputs a dict with ["pixel_values": Tensor, "labels": Tensor] in each output.

        :param image_paths: Paths to the images to be loaded (not directories, specific file paths!)
        :param label_rows: Rows from the label.csv file that correspond to the loaded images
        :param light_weight: use a smaller dataset - used for debugging, defaults to False
        """

        if light_weight:
            self.images = images[:light_weight_amount]
            self.labels = labels[:light_weight_amount]
        else:
            self.images = images
            self.labels = labels
        self.transform = transforms.ToTensor()
        self.processor = ViTImageProcessor().from_pretrained("google/vit-base-patch16-224")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        sample = Image.open(self.images[idx])
        # image = torch.flatten(self.transform(image))
        sample = self.processor(sample, return_tensors="pt")
        sample["labels"] = torch.tensor(self.labels[idx])
        return sample


class CelebADataModule:
    def __init__(
        self,
        batch_size: int = 64,
        processed_data_dir=TESTING_DATA_DIR,
    ):
        """Custom data module class for the CelebA dataset. Used for processing
        & loading of data, train/test splitting and constructing dataloaders.

        :param raw_data_dir: Path object leading to raw data, defaults to "path/to/dir"
        :param processed_data_dir: _description_, defaults to "path/to/dir"
        :param batch_size: _description_, defaults to 64
        """
        super().__init__()
        self.raw_data_dir = RAW_DATA_DIR
        self.processed_data_dir = Path(processed_data_dir)

        self.processed_labels_path = Path.joinpath(self.processed_data_dir, "labels.csv")
        self.processed_images_path = Path.joinpath(self.processed_data_dir, "images/")

        self.batch_size = batch_size

    def setup(
        self,
        use_portion_of_dataset=1.0,
        train_val_test_split=[0.6, 0.2, 0.2],
        light_weight=False,
        light_weight_amount=LIGHT_WEIGHT_AMOUNT,
    ):
        """Setup the data module, loading .jpg images from data/processed/ and splitting
        training, testing, and validation data.

        Note: if use_percent_of_dataset == 1.0, data will be split
        according to the recommended indices:
            - 1-162770: Training
            - 162771-182637: Validation,
            - 182638-202599 Testing.

        :param use_percent_of_dataset: portion of original dataset to use, defaults to 1.0
        :param train_val_test_split: how to split training, validation
        and test data if use_percent_of_dataset != 1.0, defaults to [0.6, 0.2, 0.2]
        :param light_weight: use a smaller dataset - used for debugging, defaults to False
        """

        # Load labels & image paths
        self.labels = np.genfromtxt(
            self.processed_labels_path,
            delimiter=",",
        )
        images = sorted((self.processed_images_path).glob("*.jpg"))

        # Calculate portion & splits of dataset
        available_data = math.floor(len(images) * use_portion_of_dataset)
        images = images[:available_data]
        train_idx = [
            162770
            if use_portion_of_dataset == 1.0 and len(images) == MAX_DATASET_LENGTH
            else math.floor(available_data * train_val_test_split[0])
        ]
        val_idx = [
            182637
            if use_portion_of_dataset == 1.0 and len(images) == MAX_DATASET_LENGTH
            else math.floor(available_data * (train_val_test_split[0] + train_val_test_split[1]))
        ]
        print(f"Splitting train/val/test as: [{train_idx[0]}, {val_idx[0]-train_idx[0]}, {len(images)-val_idx[0]}]")

        # Create datasets based on splits
        self.train_dataset = CustomImageDataset(
            images[: train_idx[0]],
            self.labels[: train_idx[0]],
            light_weight,
            light_weight_amount,
        )
        self.val_dataset = CustomImageDataset(
            images[train_idx[0] : val_idx[0]],
            self.labels[train_idx[0] : val_idx[0]],
            light_weight,
            light_weight_amount,
        )
        self.test_dataset = CustomImageDataset(
            images[val_idx[0] :],
            self.labels[val_idx[0] :],
            light_weight,
            light_weight_amount,
        )

    def train_dataloader(self):
        """Return a train dataloader with the requested split specified in self.setup()

        :return: a DataLoader object with the train data as (label, image)
        """
        return DataLoader(self.train_dataset, batch_size=self.batch_size)

    def val_dataloader(self):
        """Return the evaluation set dataloader with the requested split specified in self.setup()

        :return: a DataLoader object with the val data as (label, image)
        """
        return DataLoader(self.val_dataset, batch_size=self.batch_size)

    def test_dataloader(self):
        """Return a test dataloader with the requested split specified in self.setup()

        :return: a DataLoader object with the test data as (label, image)
        """
        return DataLoader(self.test_dataset, batch_size=self.batch_size)

    def process_data(self, reduced=False):  # pragma: no cover
        """Process images in the raw_data_dir directory and output them into
        the processed_data_dir directory as .jpg files.

        :param reduced: Only process a reduced amount (5k samples), defaults to False
        """
        # read labels from raw data & save as labels.csv
        labels = np.genfromtxt(
            Path.joinpath(self.raw_data_dir, "list_attr_celeba.csv"),
            skip_header=1,
            delimiter=",",
        )
        # only use the Attractive attribute
        labels = labels[:, 3:4]
        # change all the labels with value -1 to 0
        labels[labels == -1] = 0
        np.savetxt(self.processed_labels_path, labels, delimiter=",", fmt="%d")
        print(f"Successfully saved labels under {self.processed_labels_path}")

        # Process images
        raw_images = sorted(Path.joinpath(self.raw_data_dir, "images_celeba").glob("*.jpg"))
        if len(raw_images) == 0:
            error_text = "Make sure the raw input images are set in the right place."
            raise Exception(
                f"No images detected in directory {Path.joinpath(self.raw_data_dir, 'images_celeba')}. {error_text}"
            )
        if reduced:  # for debugging, only process 5000 of the available images
            raw_images = raw_images[:5000]
            all_images = 5000
        else:
            all_images = len(raw_images)

        if not self.processed_images_path.exists():
            self.processed_images_path.mkdir(parents=True)

        processor = ViTImageProcessor().from_pretrained("google/vit-base-patch16-224")
        for raw_image_id, raw_image_path in enumerate(raw_images):
            if raw_image_id % 1000 == 0:
                print(f"Processed {raw_image_id} of {all_images} images")
            image = Image.open(raw_image_path)
            image_tensor = processor.preprocess(image, return_tensors=TensorType.PYTORCH)
            torchvision.utils.save_image(
                image_tensor["pixel_values"],
                Path.joinpath(self.processed_images_path, f"image_{raw_image_id}.jpg"),
            )

        print("Successfully processed all images.")

    def show_examples(self):
        example = self.train_dataset[0]
        print(example)
        return example


if __name__ == "__main__":  # pragma: no cover
    # Usage: Process Data
    datamodule = CelebADataModule()
    datamodule.process_data(reduced=True)  # Change reduced=True to process only 5k images

    # Usage: Load Data & Get Dataloaders
    datamodule.setup()
    trainloader = datamodule.train_dataloader()
    valloader = datamodule.val_dataloader()
    testloader = datamodule.test_dataloader()
    datamodule.show_examples()
