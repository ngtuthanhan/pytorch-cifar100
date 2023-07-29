#test.py
#!/usr/bin/env python3

""" test neuron network performace
print top1 and top5 err on test dataset
of a model

author baiyu
"""
import numpy as np
import argparse

from matplotlib import pyplot as plt

import torch
import torchvision.transforms as transforms
from torch.utils.data import DataLoader

from conf import settings
from utils import get_network, get_test_dataloader
import torch.quantization
from torch.profiler import profile, record_function, ProfilerActivity


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-net', type=str, required=True, help='net type')
    parser.add_argument('-weights', type=str, required=True, help='the weights file you want to test')
    parser.add_argument('-gpu', action='store_true', default=False, help='use gpu or not')
    parser.add_argument('-b', type=int, default=16, help='batch size for dataloader')
    args = parser.parse_args()

    net = get_network(args)

    cifar100_test_loader = get_test_dataloader(
        settings.CIFAR100_TRAIN_MEAN,
        settings.CIFAR100_TRAIN_STD,
        #settings.CIFAR100_PATH,
        num_workers=4,
        batch_size=args.b,
    )

    net.load_state_dict(torch.load(args.weights))
    print(net)
    net.eval()


    # Prepare the model for quantization
    # net.qconfig = torch.quantization.get_default_qconfig()
    net_prepared = torch.quantization.prepare(net,  inplace = False)

    # Quantize the model
    net_quantized = torch.quantization.convert(net_prepared, inplace=False)
    torch.save(net_quantized.state_dict(), '123.pth')
    correct_1 = 0.0
    correct_5 = 0.0
    total = 0

    starter, ender = starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    repetitions = len(cifar100_test_loader)
    timings=np.zeros((repetitions,1))

    with torch.no_grad():
        for n_iter, (image, label) in enumerate(cifar100_test_loader):
            print("iteration: {}\ttotal {} iterations".format(n_iter + 1, len(cifar100_test_loader)))

            if args.gpu:
                image = image.cuda()
                label = label.cuda()
                # print('GPU INFO.....')
                # print(torch.cuda.memory_summary(), end='')

            with profile(activities=[ProfilerActivity.CPU], profile_memory=True, record_shapes=True) as prof:
                starter.record()
                output = net_quantized(image)
                ender.record()

            # WAIT FOR GPU SYNC
            torch.cuda.synchronize()
            curr_time = starter.elapsed_time(ender)
            timings[n_iter] = curr_time
            _, pred = output.topk(5, 1, largest=True, sorted=True)

            label = label.view(label.size(0), -1).expand_as(pred)
            correct = pred.eq(label).float()

            #compute top 5
            correct_5 += correct[:, :5].sum()

            #compute top1
            correct_1 += correct[:, :1].sum()

    if args.gpu:
        print('GPU INFO.....')
        print(torch.cuda.memory_summary(), end='')

    print()
    print("Average inference time (ms)/image: ", np.sum(timings) / repetitions)
    print("Top 1 err: ", 1 - correct_1 / len(cifar100_test_loader.dataset))
    print("Top 5 err: ", 1 - correct_5 / len(cifar100_test_loader.dataset))
    print("Parameter numbers: {}".format(sum(p.numel() for p in net.parameters())))
    # print(prof.key_averages().table(sort_by="cpu_memory_usage", row_limit=10))

