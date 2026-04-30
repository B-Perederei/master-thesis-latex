import argparse
import os
import pathlib
import time

import torch
import torch.nn as nn
import torchattacks

import models
import config
import pruning
from utils import set_arch_name, load_model, AverageMeter
from data import DataLoader
from cifar_train import validate
import wandb

def get_attacks(model):
    eps = 8/255 
    alpha = 2/255
    steps = 10
    
    return {
        "FGSM":   torchattacks.FGSM(model, eps=eps),
        "PGD":    torchattacks.PGD(model, eps=eps, alpha=alpha, steps=steps),
        "MIFGSM": torchattacks.MIFGSM(model, eps=eps, steps=steps, decay=1.0),
        "DIFGSM": torchattacks.DIFGSM(model, eps=eps, alpha=alpha, steps=steps, diversity_prob=0.5, resize_rate=0.9),
        "TIFGSM": torchattacks.TIFGSM(model, eps=eps, alpha=alpha, steps=steps, diversity_prob=0.5),
        # "APGD":   torchattacks.APGD(model, eps=eps, steps=steps, norm='Linf'),
        # "CW": torchattacks.CW(model, c=1, steps=1000),
        # "APGD_L2": torchattacks.APGD(model, norm='L2'),
        # "AutoAttack": torchattacks.AutoAttack(model, norm='Linf', version='standard')
        # "Square": torchattacks.Square(model, norm='Linf', eps=eps, n_queries=5000, n_restarts=1),
    }

class ModelWrapper(nn.Module):
    def __init__(self, model, args):
        super(ModelWrapper, self).__init__()
        self.model = model
        self.args = args

    def forward(self, x):
        if self.args.method == 'full_model':
            return self.model(x)
        else:
            return self.model(x, 1, self.args.n_bits, self.args.acti_n_bits, self.args.acti_quan)

def main(args):
    
    if args.cuda and not torch.cuda.is_available():
        raise Exception('No GPU found, please run without --cuda')
    os.environ['CUDA_VISIBLE_DEVICES'] = args.cu_num
    
    arch_name = set_arch_name(args)
    print(f"====> creating model '{arch_name}'")

    if not args.prune:
        model, image_size = models.__dict__[args.arch](data=args.dataset, num_layers=args.layers,
                                                        width_mult=args.width_mult,
                                                        depth_mult=args.depth_mult,
                                                        model_mult=args.model_mult)
    elif args.prune:
        pruner = pruning.__dict__[args.pruner]
        model, image_size = pruning.models.__dict__[args.arch](data=args.dataset, num_layers=args.layers,
                                                   width_mult=args.width_mult,
                                                   depth_mult=args.depth_mult,
                                                   model_mult=args.model_mult,
                                                   mnn=pruner.mnn,
                                                   n_bit = args.n_bits)
    assert model is not None, 'Unavailable model parameters!! exit...'

    if args.cuda:
        model = model.cuda()
        model = nn.DataParallel(model, device_ids=args.gpuids, output_device=args.gpuids[0])
        torch.backends.cudnn.benchmark = True

    # Load checkpoint
    ckpt_file = pathlib.Path('checkpoint') / arch_name / args.dataset / args.save
    assert os.path.isfile(ckpt_file), f'==> no checkpoint found "{ckpt_file}"'
    print(f"===> Loading Checkpoint '{ckpt_file}'")
    strict = False if args.prune else True
    load_model(model, ckpt_file, main_gpu=args.gpuids[0], use_cuda=args.cuda, strict=strict)
    print(f"===> Loaded Checkpoint '{ckpt_file}'")

    model.eval() # Set model to evaluation mode

    # Data loading
    print('===> Load data for evaluation...')
    _, val_loader = DataLoader(args.batch_size, args.dataset, args.workers, args.datapath, image_size, args.cuda)
    print('===> Data loaded...')

    validate(args, val_loader, 0, model, nn.CrossEntropyLoss())

    wrapped_model = ModelWrapper(model, args)
    # Initialize attack
    attacks = get_attacks(wrapped_model)

    # Evaluate on adversarial examples
    correct = 0
    total = 0
    start_time = time.time()

    for attack_name, attack in attacks.items():
        for i, (images, labels) in enumerate(val_loader):
            if args.cuda:
                images, labels = images.cuda(), labels.cuda()

            # Generate adversarial images
            adv_images = attack(images, labels)

            # Predict on adversarial images
            outputs = wrapped_model(adv_images)
            _, predicted = torch.max(outputs.data, 1)
            
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        elapsed_time = time.time() - start_time
        final_accuracy = 100 * correct / total
        
        print()
        print(f'====> Accuracy under {attack_name} attack: {final_accuracy:.2f}%')
        print(f'====> Total evaluation time: {elapsed_time:.2f} seconds')

if __name__ == '__main__':
    args = config.config()
    main(args)
