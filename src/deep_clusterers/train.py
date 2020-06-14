import os

import hydra
import torch
from hydra import utils
from torch import nn
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

from src.clusterers.deep_kmeans import DeepKmeans
from src.datasets.custom_image_folder import CustomImageFolder
from src.deep_clusterers import models
from src.deep_clusterers.pseudo_labels import reassign_labels
from src.utils import checkpoint_utils
from src.utils.pyutils import AverageMeter

use_gpu = torch.cuda.is_available()


def train(dataset_cfg, model_cfg, training_cfg, debug_root=None):
    image_root_folder = os.path.join(utils.get_original_cwd(), dataset_cfg.image_root_folder)
    groundtruth_label_file = os.path.join(utils.get_original_cwd(), dataset_cfg.groundtruth_label_file)
    learning_rate = 1e-3

    img_transform = transforms.Compose([
        transforms.Resize((training_cfg.img_size, training_cfg.img_size)),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])

    dataset = CustomImageFolder(image_root_folder, transform=img_transform,
                                sample_size=dataset_cfg.sample_size)

    model = models.__dict__[model_cfg.name](num_classes=training_cfg.n_clusters)

    model, already_trained_epoch = checkpoint_utils.load_latest_checkpoint(model, training_cfg.checkpoint, use_gpu)
    if use_gpu:
        model = model.cuda()
    deep_kmeans = DeepKmeans(groundtruth_label_file, n_clusters=training_cfg.n_clusters,
                             debug_root=debug_root)

    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-5)
    losses = AverageMeter()
    os.makedirs(os.path.dirname(training_cfg.log_file), exist_ok=True)
    os.makedirs(debug_root, exist_ok=True)
    for epoch in range(already_trained_epoch + 1, training_cfg.num_epochs):
        dataset, kmeans_loss, acc, informational_acc = reassign_labels(model, dataset, deep_kmeans,
                                                                       debug_root=debug_root, epoch=epoch)
        model.train()
        dataloader = DataLoader(dataset, batch_size=training_cfg.batch_size, shuffle=True, num_workers=4,
                                drop_last=True)
        print('epoch [{}/{}] started'.format(epoch, training_cfg.num_epochs))
        for data in tqdm(dataloader, total=len(dataset) / training_cfg.batch_size):
            img, y, _ = data
            if use_gpu:
                img = Variable(img).cuda(non_blocking=True)
                y = y.cuda(non_blocking=True)
            # ===================forward=====================
            y_hat = model(img)
            loss = criterion(y_hat, y)
            # record loss
            losses.add({'loss_%s' % epoch: loss.item() / img.size(0)})
            # ===================backward====================
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        # ===================log========================
        log = 'epoch [{}/{}],\t' \
              'loss:{:.4f},\t' \
              'kmeans loss:{:.4f}\t' \
              'acc:{:.4f}\t' \
              'informational acc:{:.4f}\n'.format(epoch, training_cfg.num_epochs, losses.get('loss_%s' % epoch),
                                                  kmeans_loss, acc,
                                                  informational_acc)
        print(log)

        with open(training_cfg.log_file, mode='a') as f:
            f.write(log)
        if epoch % 5 == 0:
            checkpoint_utils.save_checkpoint(model, training_cfg.checkpoint, epoch)
    if use_gpu:
        torch.cuda.empty_cache()


@hydra.main(config_path="conf/train.yaml")
def main(cfg):
    print('Training Starting')
    train(cfg.dataset, cfg.model, cfg.training, debug_root=cfg.debug_root)
    print('Training Finished')


if __name__ == '__main__':
    main()
