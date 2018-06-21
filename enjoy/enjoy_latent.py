from __future__ import print_function, division, absolute_import

import argparse
import json
import os

import numpy as np
import cv2
import torch
from sklearn.neighbors import KNeighborsClassifier

from preprocessing.utils import deNormalize
from models import CNNAutoEncoder, CNNVAE
from utils import detachToNumpy

VALID_MODEL = ['vae', 'autoencoder', 'priors']

def getImage(srl_model, mu, device):
    """
    Gets an image for a chosen mu value using the srl_model
    :param srl_model: (Pytorch model)
    :param mu: ([float]) the mu vector from latent space
    :param device: (pytorch device)
    :return: ([float])
    """
    with torch.no_grad():
        mu = torch.from_numpy(np.array(mu).reshape(1, -1)).to(torch.float)
        mu = mu.to(device)

        net_out = srl_model.decode(mu)

        img = detachToNumpy(net_out)[0].T

    img = deNormalize(img)
    return img[:, :, ::-1]


def main():
    parser = argparse.ArgumentParser(description="latent space enjoy")
    parser.add_argument('--log-dir', default='', type=str, help='directory to load model')
    parser.add_argument('--no-cuda', default=False, action="store_true")

    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and (not args.no_cuda) else "cpu")

    # making sure you chose the right folder
    assert os.path.exists(args.log_dir), "Error: folder '{}' does not exist".format(args.log_dir)

    srl_model_type = None
    for name, filename in zip(['priors', 'vae', 'autoencoder'], ['', '_vae', '_ae']):

        filename = "srl{}_model.pth".format(filename)
        if os.path.exists(args.log_dir + filename):
            srl_model_type = name
            model_path = args.log_dir + filename

    assert srl_model_type is not None, "Error: the folder did not contain any \"srl_model.pth\", could not determine model type."
    print("Found srl model type: " + srl_model_type)

    # is this a valid model
    assert srl_model_type in VALID_MODEL, "Error: '{}' model is not supported."

    if srl_model_type == 'priors':
        data = json.load(open(args.log_dir + 'image_to_state.json'))
        state_dim = len(list(data.values())[0])

    # model param and info
    if srl_model_type != 'priors':
        assert os.path.exists(
            args.log_dir + "exp_config.json"), "Error: could not find 'exp_config.json' in '{}'".format(
            args.log_dir)

        data = json.load(open(args.log_dir + 'exp_config.json'))
        try:
            state_dim = data["state-dim"]
        except KeyError:
            # old format
            state_dim = data["state_dim"]

        # loading the model
        if srl_model_type == "autoencoder":
            srl_model = CNNAutoEncoder(state_dim)
        elif srl_model_type == "vae":
            srl_model = CNNVAE(state_dim)
        srl_model.eval()
        srl_model.load_state_dict(torch.load(model_path))
        srl_model.to(device)

    else:

        srl_model_knn = KNeighborsClassifier()

        # Load all the points and images, find bounds and train KNN model
        X = np.array(list(data.values())).astype(float)
        y = list(data.keys())
        srl_model_knn.fit(X, np.arange(X.shape[0]))

        min_X = np.min(X, axis=0)
        max_X = np.max(X, axis=0)

    # opencv gui setup
    cv2.namedWindow(srl_model_type, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(srl_model_type, 500, 500)
    cv2.namedWindow('sliders')
    # add a slider for each component of the latent space
    for i in range(state_dim):
        # the sliders MUST be between 0 and max, so we placed max at 100, and start at 50
        # So that when we substract 50 and divide 10 we get [-5,5] for each component
        cv2.createTrackbar(str(i), 'sliders', 50, 100, (lambda a: None))

    # run the param through the network
    while 1:
        # stop if escape is pressed
        k = cv2.waitKey(1) & 0xFF
        if k == 27:
            break

        # make the image
        mu = []
        for i in range(state_dim):
            mu.append(cv2.getTrackbarPos(str(i), 'sliders'))
        if srl_model_type != 'priors':
            mu = (np.array(mu) - 50) / 10
            img = getImage(srl_model, mu, device)
        else:
            # rescale for the bounds of the priors representation, and find nearest image
            img_path = y[srl_model_knn.predict([(np.array(mu) / 100) * (max_X - min_X) + min_X])[0]]
            # Remove trailing .jpg if present
            img_path = img_path.split('.jpg')[0]
            img = cv2.imread("data/" + img_path + ".jpg")

        # stop if user closed a window
        if (cv2.getWindowProperty(srl_model_type, 0) < 0) or (cv2.getWindowProperty('sliders', 0) < 0):
            break

        cv2.imshow(srl_model_type, img)

    # gracefully close
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
