"""
With this package you can:
1. Use gradient descent algorithm to minimize a given loss function.
2. Evaluate a custom loss function (called 'cnstr_glr') and its derivate.
3. Use GD and a custom loss fucntion to fit a similarity graph to any data represented by vectors and their corresponding class labels.
4. Use the optimized similarity graph (or more exactly, the optimized metric matrix M) to predict labels of validation data points.
5. Measure validation accuracy.
6. Measure running times of all gradient descent iterations. Three different time intervals are measured: 
        1. time to execute a whole iteration
        2. time to evaluate loss and its derivative inside each iteration
        3. time to find an optimized step size in each iteration
7. Measure the time it takes to predict validation labels.

Note: time and space are used efficiently. No edges exist between same labeled nodes. Number of edges between different-labeled nodes can be controlled.
Autorun and some visualization utilities are also provided. 
Autorun functions are named 'fit_graph' (for learning phase) and 'get_acc' (for validation phase).
Used as a block in Yasaman's master's thesis.

New Version Changes: 
    1. Lables are assumed to be -1 for 'no spike' and 1 for 'spike'; instead of the previous 0-1 system.
    2. Loads feature vectors from disc instead of RAM, therefore less RAM is used (specially useful when all 297 movie repeats are considered).
       Uses conjugate gradient in the estimation phase to reduce time complexity.
    3. Conjugate gradient for higher speed in estimation phase.
    4. Number of edges between val. and train. nodes can be limited.

Author: Yasaman
Last modified: Dec 30, 2022
"""

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import cg
import time
import matplotlib.pyplot as plt

def get_edges_tt(x, Dt=None, seed=None):
    """
    Return a set of edges in the training similarity graph. 
    Only different-labeled nodes can be connected to each other (since the GLR loss function does not care about same-labeled nodes).
    If D=None, all different-labeled nodes are connected. 
    Otherwise, D shows the maximum number of (randomly chosen) different-labeled nodes that each node is connected to.
    Since the graph is assumed to be undirected, each edge is only noted by one (i,j) pair.

    Input: x, Dt, seed
    x - Nx1 vector of node labels (1 for 'spike'; -1 for 'no spike').
    Dt - maximum node degree (default: None, all different-labeled nodes are connected)
    seed - for random choice of edges (default: None, no new seed)

    Output: edges_tt
    edges_tt - list of (i,j) pairs representing edges. Node indices correspond with x.    
    """

    if Dt is None:
        return get_edges_tt_full(x)
    else:
        return get_edges_tt_maxdeg(x, Dt, seed)

def get_edges_tt_full(x):
    """
    Refer to documentation for 'get_edges_tt'
    """

    edges = []
    N = x.shape[0]
    for i in range(N):
        for j in range(i+1, N):
            if x[i] != x[j]:
                edges.append((i,j))
    return edges

def get_edges_tt_maxdeg(x, Dt, seed):
    """
    Refer to documentation for 'get_edges_tt'
    """

    if seed is not None:
        np.random.seed(seed)

    edges = []
    N = x.shape[0]
    degree = np.zeros(N)
    for i in range(N):
        candids = []
        for j in range(i+1, N):
            if x[i] != x[j] and degree[j] < Dt:
                candids.append(j)
        
        if (Dt-degree[i]) < len(candids):
            temp = np.random.choice(candids, size=int(Dt-degree[i]), replace=False)
        else:
            temp = np.array(candids)

        temp = [(i,j) for j in temp]   
        edges = edges + temp
        degree[i] += len(temp)
        for (i,j) in temp:
            degree[j] += 1

    return edges

def get_edges_vv(num_val, Dv=None, seed=None):
    """
    Return a set of edges between validation nodes in the similarity graph model.
    Edges are chosen randomly and Dv defines the maximum possible node degree.
    
    Inputs: num_val, Dv, seed=None
    num_val - number of validation nodes
    Dv - maximum possible node degree (default: None, all val. nodes are connected together)
    seed - for random selection of edges (default: None, no new seed)
    
    Outputs: edges_vv
    edges_vv - list of (i, j) pairs representing edges.
    """
    
    x = np.arange(num_val)
    return get_edges_tt(x, Dv, seed)

def get_edges_vt(train_lbls, num_val, Dvt=None, seed=None):
    """
    Return a set of edges between validation and training nodes. 
    Training nodes are assumed to belong to two clusters: -1 and 1.
    Each validation node is connected to exactly Dvt nodes of each cluster, 
    so there are a total of 2*Dvt edges connecting each validation node to the training nodes.
    Training nodes to be connected to each validation node are chosen randomly.
    
    Inputs: train_lbls, num_val, Dvt, seed=None
    train_lbls - training nodes' labels used for clustering (-1 for 'no spike', 1 for 'spike')
    num_val    - number of validation nodes
    Dvt        - number of edges between each validation node and each cluster (default: None, each val. node is connected to all training nodes)
    seed       - for random selection of training nodes (default: None, no new seed)
    
    Outputs: edges_vt
    edges_vt - list of (i, j) pairs indicating edges between validation and training nodes. 
               first index refers to validation nodes and second index to training nodes.
               second index corresponds to indices in train_lbls.
    """
    
    if Dvt is None:
        return get_edges_vt_full(len(train_lbls), num_val)
    else:
        return get_edges_vt_limit(train_lbls, num_val, Dvt, seed)
    
def get_edges_vt_full(num_train, num_val):
    """
    Refer to documentation for 'get_edges_vt'
    """
    
    edges_vt = []
    for i in range(num_val):
        for j in range(num_train):
            edges_vt.append((i, j))
            
    return edges_vt
    
def get_edges_vt_limit(train_lbls, num_val, Dvt, seed):
    """
    Refer to documentation for 'get_edges_vt'
    """
    
    # create lists of indices of training nodes in each cluster (-1 and 1)
    c_neg = []
    c_pos = []
    for i, j in enumerate(train_lbls):
        if j == -1:
            c_neg.append(i)
        else:
            c_pos.append(i)
    
    # the requested number of edges can not be bigger than the minimum cluster size
    max_Dvt = min(len(c_neg), len(c_pos))
    if Dvt > max_Dvt:
        Dvt = max_Dvt
    
    # choose edges randomly
    rng = np.random.default_rng(seed)
    edges_vt = []   
    for v_node in range(num_val):
        edges_vt += [(v_node, j) for j in rng.choice(c_neg, size=Dvt, replace=False)]
        edges_vt += [(v_node, j) for j in rng.choice(c_pos, size=Dvt, replace=False)]
    
    return edges_vt
    

def cnstr_glr(B, deriv, mu, x, F, edges_tt):
    """
    Compute loss function and its derivative w.r.t. B for a potentially sparse graph
    Loss = r + l  s.t.
           r = x.T @ L @ x , 
           l = mu * tr(M)
    where L is the graph Laplacian and M = B^T @ B.
    
    Input: B, deriv, mu, x, F, edges_tt
    B - CxC matrix of parameters determining the metric matrix (M=B.T @ B)
    deriv - whether or not to compute the derivative
    mu - scalar free parameter of the loss function
    x - Nx1 vector of image labels (1 for 'spike'; -1 for 'no spike').
    F - CxN matrix of feature vectors for all training images
    edges_tt - list of (i,j) pairs representing edges. Node indices correspond with x.    
    
    Output: if deriv: E, dE
                else: E
    E - loss value with current B
    dE - derivative of loss function w.r.t. B at current B
    """

    C = B.shape[0]
    N = x.shape[0]
    M = B.T @ B

    # init
    if deriv:
        drdM = np.zeros((C,C))    
    r = 0

    for (i,j) in edges_tt:
        # compute  r
        temp = F[:,i] - F[:,j]
        wij = np.exp(-1 * (temp.T @ M @ temp))
        r += wij

        if deriv:
            # compute drdM
            for s in range(C):
                for t in range(s, C):
                    der = wij * temp[s] * temp[t]
                    drdM[s,t] +=  der
                    drdM[t,s] = drdM[s,t]
    r *= 4
    if deriv:
        drdM *= (-4)

    # compute l and E
    E = r + mu * np.trace(M)

    if deriv:
        # compute dEdB
        dEdB = 2 * B @ (drdM +  mu * np.eye(C))
        del M
        del drdM
        return E, dEdB
    
    return E

def gradient_descent(loss_func, opt_params, show_nrmdE = False):
    """
    Learn a set of parameters using gradient descent.

    Inputs: loss_func, opt_params
    loss_func - loss function to use for training; it should only take one input which is optimization parameter
    opt_params - parameters of the training algorithm:
        'epsilon0': starting learning rate for GD
        'epsilon_decay': decay factor for GD learning rate
        'epsilon_jump': jump factor for GD learning rate
        'Theta0': initial value for the parameters
        'num_its': maximum number of iterations to run
        'check_freq': how frequently to compute and print out statistics of learning
        'print_checks': print info out when checkpointing
        'force_all_its': wether or not to run the maximum number of iterations (default: False)
        'threshod': ratio which stops the process if the loss improvment becomes less than (default: 0.01)
    show_nrmdE - whether or not to print norm of dE

    Outputs: Theta, stats
    Theta - parameters at the end of optimization
    stats - dictionary of various statistics computed during training to be used
            for visualization and analysis
    """

    # Optimization parameters in opt_params
    epsilon0 = opt_params['epsilon0']
    epsilon_decay = opt_params['epsilon_decay']
    epsilon_jump = opt_params['epsilon_jump']
    Theta0 = opt_params['Theta0']
    num_its = opt_params['num_its']
    check_freq = opt_params['check_freq']
    print_checks = opt_params['print_checks']
    force_all_its = opt_params['force_all_its'] if 'force_all_its' in opt_params else False
    threshold = opt_params['threshold'] if 'threshold' in opt_params else 0.01
    
    check_its = []
    # check_times = []
    # check_Thetas = []
    train_losss = []
    it_times = []
    stepsizeloop_times = []
    eval_times = []
    epsilon = epsilon0
    start_t = time.time()
    Theta = Theta0
    it = 0
    new_E = 0
    E = 1
    for it in range(num_its):
  
        # if the loss is not significantly improved, end the algorithm
        if (not force_all_its) and (E-new_E)/E <= threshold:
            break
                
        # Compute loss and its derivative with current parameter values
        s_start_t = time.time()
        E, dEdTheta = loss_func(Theta, deriv=True)
        eval_times.append(time.time() - s_start_t)

        # Find epsilon which decreases train loss
        s_start_t = time.time()
        epsilon *= epsilon_jump
        
        new_E = np.inf
        while new_E > E:
            # Update parameters with the GD update
            Theta1 = Theta - epsilon * dEdTheta
            new_E = loss_func(Theta1, deriv=False)
            epsilon *= epsilon_decay
            
        stepsizeloop_times.append(time.time() - s_start_t)
            
        # Replace old value of Theta with new one
        Theta = Theta1
        
        # Restore epsilon's working value 
        epsilon /= epsilon_decay

        if it%check_freq == 0 or it+1 == num_its or (E-new_E)/E <= threshold:

            # check_Thetas.append(Theta)
            check_its.append(it)
            # check_times.append(time.time() - start_t)
            train_losss.append(new_E)

            # Compute the norm of the entire gradient to monitor
            if show_nrmdE:
                new_E, dEdTheta = loss_func(Theta, deriv=True)
                nrmsq_dEdTheta = np.sum(dEdTheta**2)

            if print_checks and show_nrmdE:
                print("{:4}: eps = {:.2e};"
                      "  train loss (E) = {:5.2f};"
                      "  ||dEdTheta|| = {:5.2f}".format(it, epsilon,
                                                        new_E, 
                                                        np.sqrt(nrmsq_dEdTheta)))
            elif print_checks:
                print("{:4}: eps = {:.2e};"
                      "  train loss (E) = {:5.2f}".format(it, epsilon, new_E))

        it_times.append(time.time() - start_t)

    stats = {'check_its':check_its, # Iteration numbers of checkpoints
            # 'check_times':check_times, # wall clock time of checkpoints
            # 'check_Thetas':check_Thetas, # Theta values at checkpoints
            'it_times':it_times, # wall clock time of each iteration
            'stepsizeloop_times':stepsizeloop_times, # time to find the best stepsize in each iteration
            'eval_times':eval_times, # time to evaluate loss and its derivative at the start of each iteration
            'train_losss':train_losss} # loss of full training set at checkpoint iterations
    
    return Theta, stats


def fit_graph(dess, lbls, opt_params, mu = 0, Dt = None, seed = None, edges_tt = None):  
    """
    Fit a similarity graph to training data using the constrained GLR loss function. 
    Autorun of some functions of this package.
    
    Inputs: dess, lbls, opt_params, mu, Dt, seed, edges_tt
    dess - NxDf matrix of feature vectors of training data ponits (e.g. images)
    lbls - Nx1 vector of training labels of corresponding data points (-1 for 'no spike' and 1 for 'spike')
    opt_params - dict of parameters for gradient descent:
        'epsilon0': starting learning rate for GD
        'epsilon_decay': decay factor for GD learning rate
        'epsilon_jump': jump factor for GD learning rate
        'Theta0': initial value for the parameters. if None, it will be initialized randomly.
        'num_its': maximum number of iterations to run
        'check_freq': how frequently to compute and print out statistics of learning
        'print_checks': print info out when checkpointing
        'force_all_its': wether or not to run the maximum number of iterations (default: False)
        'threshod': ratio which stops the process if the loss improvment becomes less than (default: 0.01)
    mu - free scalar parameter of the learning objective (default: 0, only the GLR term remains in the loss function)
    Dt - maximum node degree (default: None, all different-labeled nodes are connected)
    seed - seed for random initialization of optimization parameters if it is not given (default: None, in which case no new seed is used)
    edges_tt - list of (i,j) edges of the learning similarity graph (default: None, the graph is constructed according to D)
               both (i, j) indices refer to training nodes, hence the '_tt'.

    Outputs: B, stats
    B - DfxDf matrix of optimized parameters defining the metric matrix (M = B^T @ B)
    stats - dict of gradient descent's statistics
    """


    if seed is not None:
        np.random.seed(seed)

    if opt_params['Theta0'] is None:
        num_train, f_sz = dess.shape
        opt_params['Theta0'] = 0.014142 * np.random.random_sample((f_sz,f_sz))

    if edges_tt is None:
        edges_tt = get_edges_tt(lbls, Dt, seed)

    if opt_params['print_checks']:
        print('Number of training datapoints: ' + str(dess.shape[0]))
        print('Number of features for each point: ' + str(dess.shape[1]))
        print('mu = ' + str(mu))
        print('SG edges are:', end=' ')
        print(edges_tt)

    def cnstr_glr_wrap(B, deriv=False):
        return cnstr_glr(B, deriv, mu=mu, x=lbls, F=dess.T, edges_tt=edges_tt)

    B, stats = gradient_descent(cnstr_glr_wrap, opt_params)

    return B, stats


def create_W(B, F):
    """
    Create the graph's adjacency matrix from B
    
    Input: B, F
    B - CxC matrix of parameters determining the metric matrix (M = B.T @ B)
    F - NxC matrix of feature vectors of training images
    
    Output: W
    W - NxN adjacency matrix of the similarity graph    
    """
    num_train = F.shape[0]
    M = B.T @ B 

    W = np.zeros((num_train, num_train))
    for i in range(num_train):
        for j in range(i+1, num_train):
            dij = (F[i] - F[j]).T @ M @ (F[i] - F[j])
            W[i][j] = np.exp(-1*dij)
            W[j][i] = W[i][j]
              
    return W

def create_L(W):
    """
    Create the graph laplacian from its adjacency matrix. L = diag(W 1) - W

    Input: W
    W - NxN adjacency matrix of a graph

    Output: L
    L - NxN graph laplacian
    """

    num_train = W.shape[0]
    D = np.diag(W @ np.ones(num_train))
    L = D - W

    return L

def in_order(W, x):
    """
    Sorts the adjacency matrix w.r.t. labels of nodes. All nodes of the same label are gathered in a block.
    Labels are sorted in ascending order.
    
    Input: W, x
    W - NxN adjacency matrix of the similarity graph
    x - Nx1 vector of labels of corresponding nodes
    
    Output: W_ord, order
    W_ord - NxN adjacency matrix where all same labeled nodes come together
    origin - Nx1 vector depicting the new order of nodes; origin[i] = index of image #i in the original random permutation
    cats - all possible labels in the order they come in W_ord
    """
    
    # get all possible labels in ascending order
    cats = sorted(list(dict.fromkeys(x)))

    # original indices of data points
    orig_i = np.arange(x.shape[0])

    # sort rows (along axis 0)
    W1 = W[x == cats[0], :]
    for i in range(1, len(cats)):
        W1 = np.append(W1, W[x == cats[i], :], axis=0)
    
    # sort columns (along axis 1)
    W_ord = W1[:, x == cats[0]]
    for i in range(1, len(cats)):
        W_ord = np.append(W_ord, W1[:, x == cats[i]], axis=1)

    # get new places of data points
    origin = orig_i[x == cats[0]]
    for i in range(1, len(cats)):
        origin = np.append(origin, orig_i[x == cats[i]], axis=0)   
    
    return W_ord, origin, cats


def extrapolate(B, train_des, val_des, train_gt, edges_vv, edges_vt):
    """
    Estimate labels of unknown vertices based on learned metric B (M = B.T @ B).
    
    Inputs: B, train_des, val_des, train_gt
    B - CxC matrix of parameters determining the metric matrix (M = B.T @ B)
    train_des - NtxC matrix of descriptors of training data points (e.g. images)
    val_des - NvxC matrix of descriptors of validation data points (e.g. images)
    train_gt - Ntx1 vector of labels of corresponding training data points (1 for 1, and -1 for 0)
    edges_vv - list of (i, j) pairs representing edges between val. nodes.
    edges_vt - list of (i, j) pairs representing edges between val. and training nodes.
    
    Output: y_est
    y_est - Nvx1 vector of estimated labels (1 for 'spike', and -1 for 'no spike')
    t - time it took to estimate labels in seconds
    """

    start_t = time.time()
    
    # find number of validation and training images
    num_train = train_des.shape[0]
    num_val = val_des.shape[0]
    f_sz = B.shape[0]
    M = B.T @ B

    # create W
    W21 = np.zeros((num_val, num_train))
    for (i, j) in edges_vt:
        Fi = val_des[i]
        Fj = train_des[j]
        Fij = Fi - Fj
        dij = Fij.T @ M @ Fij
        W21[i][j] = np.exp(-1*dij)
        
    W22 = np.zeros((num_val, num_val))
    for (i, j) in edges_vv:
        Fi = val_des[i]
        Fj = val_des[j]
        Fij = Fi - Fj
        dij = Fij.T @ M @ Fij
        W22[i][j] = np.exp(-1*dij)
        W22[j][i] = W22[i][j]
        
    # debug
    print('W21 =\n', W21)
    print('W22 =\n', W22)
            
    # create L21, L22
    L22 = np.diag((W21 @ np.ones(num_train)) + (W22 @ np.ones(num_val)))
    L22 = L22 - W22
    del W22 # to free up space
    L21 = -1*W21
    del W21 # to free up space
    
    # debug
    print('L21 =\n', L21)
    print('L22 =\n', L22)
      
    # estimate unknown labels via graph filtering
    b = -1 * (L21 @ train_gt)
    y_est, exit_code = cg(L22, b)
    assert exit_code >= 0 # negative exit code means the answer did not converge.
  
    t = time.time() - start_t
    
    return y_est, t


def extrapolate_old(B, train_des, val_des, train_gt, edges_vv, edges_vt):
    """
    Estimate labels of unknown vertices based on learned metric B (M = B.T @ B).
    
    Inputs: B, train_des, val_des, train_gt
    B - CxC matrix of parameters determining the metric matrix (M = B.T @ B)
    train_des - NtxC matrix of descriptors of training data points (e.g. images)
    val_des - NvxC matrix of descriptors of validation data points (e.g. images)
    train_gt - Ntx1 vector of labels of corresponding training data points (1 for 1, and -1 for 0)
    edges_vv - list of (i, j) pairs representing edges between val. nodes.
    edges_vt - list of (i, j) pairs representing edges between val. and training nodes.
    
    Output: y_est
    y_est - Nvx1 vector of estimated labels (1 for 'spike', and -1 for 'no spike')
    t - time it took to estimate labels in seconds
    """

    start_t = time.time()
    
    # find number of validation and training images
    num_train = train_des.shape[0]
    num_val = val_des.shape[0]
    f_sz = B.shape[0]

    # concatenate descriptors of training and validation data points
    data_des = np.append(train_des, val_des, axis=0)
    num_data = data_des.shape[0]
    assert num_data == num_train + num_val
    assert data_des.shape[1] == f_sz

    # create W
    W = create_W(B, data_des)
            
    # create L21, L22
    L = create_L(W)
    del W # to free space
    L21 = L[num_train:, :num_train]
    L22 = L[num_train:, num_train:]
    
    # estimate unknown labels via graph filtering
    # y_est = -1 * (np.linalg.inv(L22) @ L21 @ train_gt)  # this is the more complex way
    b = -1 * (L21 @ train_gt)
    y_est, exit_code = cg(L22, b)
    assert exit_code >= 0 # negative exit code means the answer did not converge.
  
    t = time.time() - start_t
    
    return y_est, t


def get_acc(B, train_des, train_y, val_des, val_y, Dv=None, Dvt=None, seed=None, show_edges=True):
    """
    Estimate labels of unknown vertices based on learned metric B (M = B.T @ B), and calculate accuracy.
    Autorun of 'extrapolate' function in this package.
    
    Inputs: B, train_des, train_y, val_des, val_y
    B - CxC matrix of parameters determining the metric matrix (M = B.T @ B)
    train_des - NtxC matrix of descriptors of training data points (e.g. images)
    train_y - Ntx1 vector of labels of corresponding training data points (-1 for 'no spike' and 1 for 'spike')
    val_des - NvxC matrix of descriptors of validation data points (e.g. images)
    val_y - Nvx1 vector of labels of corresponding training data points (-1 for 'no spike' and 1 for 'spike')
    Dv - maximum possible node degree (default: None, all val. nodes are connected together)
    Dvt - number of edges between each validation node and each cluster (default: None, each val. node is connected to all training nodes)
    seed - for random selection of edges (default: None, no new seed)
    show_edges - whether or not to show chosen edges

    Output: y_est, acc
    acc - accuracy a.k.a. percentage of correctly estimated labels over all validation vertices
    y_est - Nvx1 vector of estimated labels
    t - time it took to estimate validation labels in seconds
    """
    
    num_val = len(val_y)
    edges_vv = get_edges_vv(num_val, Dv, seed)
    edges_vt = get_edges_vt(train_y, num_val, Dvt, seed)
        
    if show_edges:
        print('edges between val. nodes:\n', edges_vv)
        print('edges between val. and train. nodes:\n', edges_vt)

    y_est, t = extrapolate(B, train_des, val_des, train_y, edges_vv, edges_vt)

    y_th = (y_est > 0).astype(int) * 2 - 1
    acc = np.sum(y_th == val_y)/len(val_y)

    return acc, y_est, t










###########################
# Visualization Utilities #
###########################

def display_matrix(M, title=None):
    """
    Display a color map of a matrix's entries.
    
    Inputs: M, title=None
    M - matrix to be displayed
    title - title of the figure
    """
    
    plt.figure(figsize=(4,4))
    plt.imshow(M)
    plt.colorbar()
    if title is not None:
        plt.title(title)


def hist_of_entries(M, num_bins, lx=None, lbl=None, zeroline=False, peakline=False):
    """
    Draw a histogram of a given matrix's entries.

    Inputs: M, num_bins, lx=None, lbl=None, zeroline=False, peakline=False
    M - matrix whose histogram of entries is drawn
    num_bins - number of bins in the histogram
    lx - defines interval of x-axis to be shown [-lx, lx]. 'None' to disable x-axis limiting.
    lbl - title of the histogram
    zeroline - wether or not to draw a vertical line at x=0
    peakline - wether or not to draw a vertical line at the histogram's peak

    Outputs: 
    """
    
    plt.figure(figsize=(4,4))
    histvals, bins, _ = plt.hist(M.reshape(-1),num_bins)
    
    if lx is not None:
        plt.xlim([-lx, lx])
    
    if lbl is not None:
        _ = plt.title(lbl)
        
    if zeroline:
        plt.axvline(x = 0, color = 'm', label = 'zero line')
        
    if peakline:
        peak_x = (bins[np.argmax(histvals)] + bins[np.argmax(histvals)+1])/2
        plt.axvline(x = peak_x, color = 'r', label = 'peak line')
        return peak_x, np.max(histvals) # most repeated M value and the number of its repeats



