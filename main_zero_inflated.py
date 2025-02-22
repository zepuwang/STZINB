from __future__ import division
import torch
from torch.autograd import Variable
import numpy as np
import torch.nn.functional as F
import torchvision
from torchvision import transforms
import torch.optim as optim
from torch import nn
import matplotlib.pyplot as plt
from utils import generate_dataset, get_normalized_adj, get_Laplace, calculate_random_walk_matrix,nb_zeroinflated_nll_loss,nb_zeroinflated_draw,nb_MDN_nll_loss
from model import *
import random,os,copy
import math
import tqdm
from scipy.stats import nbinom
import pickle as pk
import os
import argparse
import logging
# Parameters

parser = argparse.ArgumentParser(description='STGCN')
parser.add_argument('--enable-cuda', action='store_true',
                    help='Enable CUDA')
parser.add_argument('--data-dir', type=str,
                    default='./ny_data_full_5min',
                    help='Directory to save the best model')
parser.add_argument('--save-name', type=str,
                    default='pth/model.pth')
parser.add_argument('--seed', type=int,
                    default=0)
parser.add_argument('--log-dir', type=str,
                    default='log/origin.txt')
args = parser.parse_args()
args.device = None
if args.enable_cuda and torch.cuda.is_available():
    args.device = torch.device('cuda')
else:
    args.device = torch.device('cpu')
device = args.device
torch.manual_seed(args.seed)

# Set loggers
logger = logging.getLogger('Model training')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(args.log_dir,'w')
handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

#torch.device('cuda') 
A = np.load(args.data_dir + '/adj_rand0.npy') # change the loading folder
X = np.load(args.data_dir + '/cta_samp_rand0.npy')

num_timesteps_output = 4 
num_timesteps_input = num_timesteps_output

space_dim = X.shape[1]
batch_size = 4
hidden_dim_s = 70
hidden_dim_t = 7
rank_s = 20
rank_t = 4
n_gaussian = 2

epochs = 500 #500

# Initial networks
TCN1 = B_TCN(space_dim, hidden_dim_t, kernel_size=3).to(device=device)
TCN2 = B_TCN(hidden_dim_t, rank_t, kernel_size = 3, activation = 'linear').to(device=device)
TCN3 = B_TCN(rank_t, hidden_dim_t, kernel_size= 3).to(device=device)
TNB = MDN(hidden_dim_t,space_dim,n_gaussian).to(device=device)
#NBNorm_ZeroInflated(hidden_dim_t,space_dim).to(device=device)
SCN1 = D_GCN(num_timesteps_input, hidden_dim_s, 3).to(device=device)
SCN2 = D_GCN(hidden_dim_s, rank_s, 2, activation = 'linear').to(device=device)
SCN3 = D_GCN(rank_s, hidden_dim_s, 2).to(device=device)
SNB = MDN(hidden_dim_s,num_timesteps_output,n_gaussian).to(device=device)
#NBNorm_ZeroInflated(hidden_dim_s,num_timesteps_output).to(device=device)
STmodel = ST_MDN(SCN1, SCN2, SCN3, TCN1, TCN2, TCN3, SNB,TNB).to(device=device)
#ST_NB_ZeroInflated(SCN1, SCN2, SCN3, TCN1, TCN2, TCN3, SNB,TNB).to(device=device)

# Load dataset

X = X.T
X = X.astype(np.float32)
X = X.reshape((X.shape[0],1,X.shape[1]))

split_line1 = int(X.shape[2] * 0.6)
split_line2 = int(X.shape[2] * 0.7)
print(X.shape,A.shape)

# normalization
max_value = np.max(X[:, :, :split_line1])

train_original_data = X[:, :, :split_line1]
val_original_data = X[:, :, split_line1:split_line2]
test_original_data = X[:, :, split_line2:]
training_input, training_target = generate_dataset(train_original_data,
                                                    num_timesteps_input=num_timesteps_input,
                                                    num_timesteps_output=num_timesteps_output)
val_input, val_target = generate_dataset(val_original_data,
                                            num_timesteps_input=num_timesteps_input,
                                            num_timesteps_output=num_timesteps_output)
test_input, test_target = generate_dataset(test_original_data,
                                            num_timesteps_input=num_timesteps_input,
                                            num_timesteps_output=num_timesteps_output)
print('input shape: ',training_input.shape,val_input.shape,test_input.shape)


A_wave = get_normalized_adj(A)
A_q = torch.from_numpy((calculate_random_walk_matrix(A_wave).T).astype('float32'))
A_h = torch.from_numpy((calculate_random_walk_matrix(A_wave.T).T).astype('float32'))
A_q = A_q.to(device=device)
A_h = A_h.to(device=device)
# Define the training process
# criterion = nn.MSELoss()
optimizer = optim.Adam(STmodel.parameters(), lr=1e-5)
training_nll   = []
validation_nll = []
validation_mae = []

for epoch in range(epochs):

    ## Step 1, training
    """
    # Begin training, similar training procedure from STGCN
    Trains one epoch with the given data.
    :param training_input: Training inputs of shape (num_samples, num_nodes,
    num_timesteps_train, num_features).
    :param training_target: Training targets of shape (num_samples, num_nodes,
    num_timesteps_predict).
    :param batch_size: Batch size to use during training.
    """
    permutation = torch.randperm(training_input.shape[0])
    epoch_training_losses = []
    for i in range(0, training_input.shape[0], batch_size):
        STmodel.train()
        optimizer.zero_grad()

        indices = permutation[i:i + batch_size]
        X_batch, y_batch = training_input[indices], training_target[indices]
        X_batch = X_batch.to(device=device)
        y_batch = y_batch.to(device=device)

        

        pi_train,pi_g_train,mu_g_train,sigma_g_train = STmodel(X_batch,A_q,A_h)
        #n_train,p_train,pi_train = STmodel(X_batch,A_q,A_h)


        loss = nb_MDN_nll_loss(y_batch,pi_train, pi_g_train,mu_g_train,sigma_g_train)        
        #loss = nb_zeroinflated_nll_loss(y_batch,n_train,p_train,pi_train)
        loss.backward()
        optimizer.step()
        epoch_training_losses.append(loss.detach().cpu().numpy())
        
    training_nll.append(sum(epoch_training_losses)/len(epoch_training_losses))
    # print(sum(epoch_training_losses)/len(epoch_training_losses))



    ## Step 2, validation
    
    # with torch.no_grad():
    #     STmodel.eval()
    #     val_input = val_input.to(device=device)
    #     val_target = val_target.to(device=device)

    #     pi_val,pi_g_val,mu_g_val,sigma_g_val = STmodel(val_input,A_q,A_h)
    #     #n_val,p_val,pi_val = STmodel(val_input,A_q,A_h)
    #     #print('Pi_val,mean,min,max',torch.mean(pi_val),torch.min(pi_val),torch.max(pi_val))

    #     val_loss = nb_MDN_nll_loss(val_target,pi_val, pi_g_val,mu_g_val,sigma_g_val)
    #     #val_loss    = nb_zeroinflated_nll_loss(val_target,n_val,p_val,pi_val).to(device="cpu")
    #     validation_nll.append(np.asscalar(val_loss.detach().numpy()))
       
    #     # Calculate the expectation value

    #     val_pred = torch.abs(1-pi_val) *  torch.sum((pi_g_val * torch.exp(mu_g_val)),dim = -1)
    #     #print(mu_g_val[:,:,:,0])
       
    #     #print(print_errors(val_target.detach().cpu().numpy(),val_pred.detach().cpu().numpy()))
    #     #val_pred = (1-pi_val.detach().cpu().numpy())*(n_val.detach().cpu().numpy()/p_val.detach().cpu().numpy()-n_val.detach().cpu().numpy()) # pipred
    #     #print(val_pred.mean(),pi_val.detach().cpu().numpy().min())
    #     mae = torch.mean(torch.abs(val_pred - val_target.detach().cpu().numpy()))
    #     #print(mae)
    #     validation_mae.append(mae)
    #     pi_val,pi_g_val,mu_g_val,sigma_g_val = None, None, None, None

    #     val_input = val_input.to(device="cpu")
    #     val_target = val_target.to(device="cpu")
    logger.info("Epoch: {}, training loss: {}".format(epoch,training_nll[-1]))
    handler.flush()
    
    # print('Epoch: {}'.format(epoch))
    # print("Training loss: {}".format(training_nll[-1]))
    # print('Epoch %d: trainNLL %.5f; valNLL %.5f; mae %.4f'%(epoch,training_nll[-1],validation_nll[-1],validation_mae[-1]))
    if training_nll[-1] == min(training_nll):
        best_model = copy.deepcopy(STmodel.state_dict())
    checkpoint_path = "checkpoints/"
    if not os.path.exists(checkpoint_path):
        os.makedirs(checkpoint_path)
    with open("checkpoints/losses.pk", "wb") as fd:
        pk.dump((training_nll, validation_nll, validation_mae), fd)
    if np.isnan(training_nll[-1]):
        break
STmodel.load_state_dict(best_model)
torch.save(STmodel,args.save_name)
