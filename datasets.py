
# Copyright (c) Meta Platforms, Inc. and affiliates.

# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import print_function, division
from torch.utils.data import ConcatDataset
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
import numpy as np
from torchvision import datasets, models, transforms
import matplotlib.pyplot as plt
import time
import os
# import copycleclear
import torchvision
import scipy.io
from PIL import Image

import os
from torchvision import datasets, transforms

from timm.data.constants import \
    IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD, IMAGENET_INCEPTION_MEAN, IMAGENET_INCEPTION_STD
from timm.data import create_transform

def build_dataset(is_train, args):
    transform = build_transform(is_train, args)

    print("Transform = ")
    if isinstance(transform, tuple):
        for trans in transform:
            print(" - - - - - - - - - - ")
            for t in trans.transforms:
                print(t)
    else:
        for t in transform.transforms:
            print(t)
    print("---------------------------")

    if args.data_set == 'CIFAR':
        dataset = datasets.CIFAR100(args.data_path, train=is_train, transform=transform, download=True)
        nb_classes = 100
    elif args.data_set == 'IMNET':
        print("reading from datapath", args.data_path)
        root = os.path.join(args.data_path, 'train' if is_train else 'val')
        dataset = datasets.ImageFolder(root, transform=transform)
        nb_classes = 1000
    elif args.data_set == "image_folder":
        root = args.data_path if is_train else args.eval_data_path
        dataset = datasets.ImageFolder(root, transform=transform)
        nb_classes = args.nb_classes
        assert len(dataset.class_to_idx) == nb_classes

    elif args.data_set == "CUB":
        print("reading from datapath", args.data_path)
        root = args.data_path
        if is_train:
            dataset = CUBDataset(image_root_path=root, transform=transform, split="train")
        else:
            dataset = CUBDataset(image_root_path=root, transform=transform, split="test")

        nb_classes = args.nb_classes
        assert len(dataset.class_to_idx) == nb_classes

    elif args.data_set == "CUB_DOG":
        # This time we will have 2 datasets
        root1 = args.data_path.split(' ')[0]
        root2 = args.data_path.split(' ')[1]
        print("reading from datapath", root1)
        print("reading from datapath", root2)
        if is_train:
            dataset1 = CUBDataset(image_root_path=root1, transform=transform, split="train")
            dataset2 = DOGDataset(image_root_path=root2, transform=transform, split="train")
            dataset = ConcatDataset([dataset1, dataset2])
        else:
            dataset1 = CUBDataset(image_root_path=root1, transform=transform, split="test")
            dataset2 = DOGDataset(image_root_path=root2, transform=transform, split="test")
            dataset = ConcatDataset([dataset1, dataset2])

        nb_classes = 320
        # assert len(dataset.class_to_idx) == nb_classes

    elif args.data_set == "FOOD":

        if is_train:
            train_df = pd.read_csv(f'{args.data_path}/annot/train_info.csv', names=['image_name', 'label'])
            train_df['path'] = train_df['image_name'].map(lambda x: os.path.join(f'{args.data_path}/train_set/', x))
            dataset = FOODDataset(train_df, transform=transform)
        else:
            val_df = pd.read_csv(f'{args.data_path}/annot/val_info.csv', names=['image_name', 'label'])
            val_df['path'] = val_df['image_name'].map(lambda x: os.path.join(f'{args.data_path}/val_set/', x))
            dataset = FOODDataset(val_df, transform=transform)
        nb_classes = 251
        # assert len(dataset.class_to_idx) == nb_classes
    else:
        raise NotImplementedError()
    print("Number of the class = %d" % nb_classes)

    return dataset, nb_classes


def build_transform(is_train, args):
    resize_im = args.input_size > 32
    imagenet_default_mean_and_std = args.imagenet_default_mean_and_std
    mean = IMAGENET_INCEPTION_MEAN if not imagenet_default_mean_and_std else IMAGENET_DEFAULT_MEAN
    std = IMAGENET_INCEPTION_STD if not imagenet_default_mean_and_std else IMAGENET_DEFAULT_STD

    if is_train:
        # this should always dispatch to transforms_imagenet_train
        transform = create_transform(
            input_size=args.input_size,
            is_training=True,
            color_jitter=args.color_jitter,
            auto_augment=args.aa,
            interpolation=args.train_interpolation,
            re_prob=args.reprob,
            re_mode=args.remode,
            re_count=args.recount,
            mean=mean,
            std=std,
        )
        if not resize_im:
            transform.transforms[0] = transforms.RandomCrop(
                args.input_size, padding=4)
        return transform

    t = []
    if resize_im:
        # warping (no cropping) when evaluated at 384 or larger
        if args.input_size >= 384:  
            t.append(
            transforms.Resize((args.input_size, args.input_size), 
                            interpolation=transforms.InterpolationMode.BICUBIC), 
        )
            print(f"Warping {args.input_size} size input images...")
        else:
            if args.crop_pct is None:
                args.crop_pct = 224 / 256
            size = int(args.input_size / args.crop_pct)
            t.append(
                # to maintain same ratio w.r.t. 224 images
                transforms.Resize(size, interpolation=transforms.InterpolationMode.BICUBIC),  
            )
            t.append(transforms.CenterCrop(args.input_size))

    t.append(transforms.ToTensor())
    t.append(transforms.Normalize(mean, std))
    return transforms.Compose(t)



class CUBDataset(torchvision.datasets.ImageFolder):
    """
    Dataset class for CUB Dataset
    """

    def __init__(self, image_root_path, caption_root_path=None, split="train", *args, **kwargs):
        """
        Args:
            image_root_path:      path to dir containing images and lists folders
            caption_root_path:    path to dir containing captions
            split:          train / testz
            *args:
            **kwargs:
        """
        image_info = self.get_file_content(f"{image_root_path}/images.txt")
        self.image_id_to_name = {y[0]: y[1] for y in [x.strip().split(" ") for x in image_info]}
        split_info = self.get_file_content(f"{image_root_path}/train_test_split.txt")
        self.split_info = {self.image_id_to_name[y[0]]: y[1] for y in [x.strip().split(" ") for x in split_info]}
        self.split = "1" if split == "train" else "0"
        self.caption_root_path = caption_root_path

        super(CUBDataset, self).__init__(root=f"{image_root_path}/images", is_valid_file=self.is_valid_file,
                                         *args, **kwargs)

    def is_valid_file(self, x):
        return self.split_info[(x[len(self.root) + 1:])] == self.split

    @staticmethod
    def get_file_content(file_path):
        with open(file_path) as fo:
            content = fo.readlines()
        return content


class DOGDataset(torchvision.datasets.ImageFolder):
    """
    Dataset class for DOG Dataset
    """

    def __init__(self, image_root_path, caption_root_path=None, split="train", *args, **kwargs):
        """
        Args:
            image_root_path:      path to dir containing images and lists folders
            caption_root_path:    path to dir containing captions
            split:          train / test
            *args:
            **kwargs:
        """
        image_info = self.get_file_content(f"{image_root_path}splits/file_list.mat")
        image_files = [o[0][0] for o in image_info]

        split_info = self.get_file_content(f"{image_root_path}/splits/{split}_list.mat")
        split_files = [o[0][0] for o in split_info]
        self.split_info = {}
        if split == 'train':
            for image in image_files:
                if image in split_files:
                    self.split_info[image] = "1"
                else:
                    self.split_info[image] = "0"
        elif split == 'test':
            for image in image_files:
                if image in split_files:
                    self.split_info[image] = "0"
                else:
                    self.split_info[image] = "1"

        self.split = "1" if split == "train" else "0"
        self.caption_root_path = caption_root_path

        super(DOGDataset, self).__init__(root=f"{image_root_path}Images", is_valid_file=self.is_valid_file,
                                         *args, **kwargs)

        ## modify class index as we are going to concat to first dataset
        self.class_to_idx = {class_: idx + 200 for idx, class_ in enumerate(self.class_to_idx)}

    def is_valid_file(self, x):
        return self.split_info[(x[len(self.root) + 1:])] == self.split

    def __getitem__(self, index):
        path, target = self.imgs[index]
        img = Image.open(os.path.join(path)).convert('RGB')
        if self.transform is not None:
            img = self.transform(img)
        if self.target_transform is not None:
            target = self.target_transform(target)

        ## modify target class index as we are going to concat to first dataset
        return img, target + 200

    @staticmethod
    def get_file_content(file_path):
        content = scipy.io.loadmat(file_path)
        return content['file_list']

    class DOGDataset(torchvision.datasets.ImageFolder):
        """
        Dataset class for DOG Dataset
        """

        def __init__(self, image_root_path, caption_root_path=None, split="train", *args, **kwargs):
            """
            Args:
                image_root_path:      path to dir containing images and lists folders
                caption_root_path:    path to dir containing captions
                split:          train / test
                *args:
                **kwargs:
            """
            image_info = self.get_file_content(f"{image_root_path}splits/file_list.mat")
            image_files = [o[0][0] for o in image_info]

            split_info = self.get_file_content(f"{image_root_path}/splits/{split}_list.mat")
            split_files = [o[0][0] for o in split_info]
            self.split_info = {}
            if split == 'train':
                for image in image_files:
                    if image in split_files:
                        self.split_info[image] = "1"
                    else:
                        self.split_info[image] = "0"
            elif split == 'test':
                for image in image_files:
                    if image in split_files:
                        self.split_info[image] = "0"
                    else:
                        self.split_info[image] = "1"

            self.split = "1" if split == "train" else "0"
            self.caption_root_path = caption_root_path

            super(DOGDataset, self).__init__(root=f"{image_root_path}Images", is_valid_file=self.is_valid_file,
                                             *args, **kwargs)

            ## modify class index as we are going to concat to first dataset
            self.class_to_idx = {class_: idx + 200 for idx, class_ in enumerate(self.class_to_idx)}

        def is_valid_file(self, x):
            return self.split_info[(x[len(self.root) + 1:])] == self.split

        def __getitem__(self, index):
            path, target = self.imgs[index]
            img = Image.open(os.path.join(path)).convert('RGB')
            if self.transform is not None:
                img = self.transform(img)
            if self.target_transform is not None:
                target = self.target_transform(target)

            ## modify target class index as we are going to concat to first dataset
            return img, target + 200

        @staticmethod
        def get_file_content(file_path):
            content = scipy.io.loadmat(file_path)
            return content['file_list']

    class FOODDataset(torch.utils.data.Dataset):
        def __init__(self, dataframe, transform):
            self.dataframe = dataframe
            self.data_transform = transform

        def __len__(self):
            return len(self.dataframe)

        def __getitem__(self, index):
            row = self.dataframe.iloc[index]
            return (
                self.data_transform(Image.open(row["path"])), row['label']
            )