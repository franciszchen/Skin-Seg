# tf_unet is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# tf_unet is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with tf_unet.  If not, see <http://www.gnu.org/licenses/>.


'''
Created on Jul 28, 2016

author: jakeret
'''
from __future__ import print_function, division, absolute_import, unicode_literals
import tensorflow.contrib as tf_contrib
from tensorflow.contrib.layers.python.layers import layers

import os
import shutil
import numpy as np
import logging
from collections import OrderedDict
from sklearn.metrics import precision_score, recall_score, accuracy_score, f1_score
import tensorflow as tf
from ops import *
from nets.tf_unet.layers import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

def Unet(x, labels, keep_prob=1.0, channels=3, n_class=2, num_layers=5, features_root=64, filter_size=3, pool_size=2,summaries=True, trainable=True, reuse=False, scope='dis'):    
    with tf.variable_scope(scope, reuse=reuse):
        print(scope)
        #if scope == 'dmlnet_0':
        weight_init = tf.random_normal_initializer(mean=0.0, stddev=0.1)
        #if scope == 'dmlnet_1':
        #    weight_init = tf.random_normal_initializer(mean=0.0, stddev=0.15)
            
        end_points = {}
        logging.info(
            "Layers {num_layers}, features {features}, filter size {filter_size}x{filter_size}, pool size: {pool_size}x{pool_size}".format(
                num_layers=num_layers,
                features=features_root,
                filter_size=filter_size,
                pool_size=pool_size))

        # Placeholder for the input image
        #with tf.variable_scope("preprocessing", reuse=reuse):
        batch_size = tf.shape(x)[0]
        nx = tf.shape(x)[1]
        ny = tf.shape(x)[2]
        in_node = x

        weights = []
        biases = []
        convs = []
        pools = OrderedDict()
        deconv = OrderedDict()
        dw_h_convs = OrderedDict()
        up_h_convs = OrderedDict()

        in_size = 1000
        size = in_size
        # down layers
        for layer in range(0, num_layers):
            with tf.variable_scope("down_conv_{}".format(str(layer)), reuse=reuse):
                features = 2 ** layer * features_root
                
                conv1 = atrous_conv2d(in_node, features, kernel=3, rate=1, pad=0, pad_type='zero', scope='atrous1')
                conv2 = atrous_conv2d(in_node, features, kernel=3, rate=2, pad=0, pad_type='zero', scope='atrous2')
                conv3 = atrous_conv2d(in_node, features, kernel=3, rate=3, pad=0, pad_type='zero', scope='atrous3')
                gamma1 = tf.get_variable("GGamma1", [1], initializer=tf.constant_initializer(1/3.0))
                gamma2 = tf.get_variable("GGamma2", [1], initializer=tf.constant_initializer(1/3.0))
                gamma3 = tf.get_variable("GGamma3", [1], initializer=tf.constant_initializer(1/3.0))
                '''tf.summary.scalar("down_conv_%d" % layer + '/gamma1', gamma1)
                tf.summary.scalar("down_conv_%d" % layer + '/gamma2', gamma2)
                tf.summary.scalar("down_conv_%d" % layer + '/gamma3', gamma3)'''
                conv = gamma1*conv1 + gamma2*conv2 + gamma3*conv3
                conv = tf_contrib.layers.batch_norm(conv,decay=0.9, epsilon=1e-05,center=True, scale=True, updates_collections=None,is_training=trainable)
                conv = tf.nn.relu(conv)

                size -= 4
                #if layer < num_layers - 1:
                pools[layer] = max_pool(conv, pool_size)
                in_node = pools[layer]
                size /= 2
                dw_h_convs[layer] = in_node
                print('down_conv',layer, dw_h_convs[layer])

        in_node = dw_h_convs[num_layers - 1]

        # up layers
        for layer in range(num_layers - 1, -1, -1):
            with tf.variable_scope("up_conv_{}".format(str(layer)), reuse=reuse):
                features = 2 ** (layer) * features_root
                stddev = np.sqrt(2 / (filter_size ** 2 * features))
                if layer != 0 and layer != 1:
                    wd = weight_variable_devonc([pool_size, pool_size, features, features// 2], stddev, weight_init, name="wd")
                    bd = bias_variable([features // 2], weight_init, name="bd")
                if layer == 0 or layer == 1:
                    wd = weight_variable_devonc([pool_size, pool_size, features, features], stddev, weight_init, name="wd")
                    bd = bias_variable([features], weight_init, name="bd")
                #h_deconv = tf.nn.relu(deconv2d(in_node, wd, pool_size,reuse=reuse) + bd)
                in_node = up_sample_bilinear(in_node, scale_factor=2)
                h_deconv = tf.nn.relu(conv2d(in_node, wd, bd, keep_prob,reuse=reuse))
                ######################
                if layer != 0 and layer != 1:
                    #h_deconv_concat, offset1 = deform_conv2d(h_deconv, dw_h_convs[layer], offset_kernel_size=3, kernel_size=3, num_outputs=features// 2, activation=tf.nn.relu, scope="adaptive_conv", reuse=reuse)
                    print('h_deconv',layer, h_deconv)
                    print('dw_h_convs[layer]',dw_h_convs[layer-1])
                    h_deconv_concat, offset1 = adaptive_deform_con2v(h_deconv, dw_h_convs[layer-1], features// 2, kernel_size=3, stride=1, trainable=trainable, name='adaptive_conv', reuse=reuse)
                    end_points['offset'+str(layer)] = offset1
                    h_deconv_concat = tf.concat([h_deconv_concat, h_deconv],axis=-1)
                ######################
                if layer == 0 or layer == 1:
                    #h_deconv_concat = atrous_conv2d(dw_h_convs[layer], features// 2, kernel=3, rate=2, pad=0, pad_type='zero', scope='atrous_conv')
                    #h_deconv_concat = tf.concat([dw_h_convs[layer], h_deconv],axis=-1)
                    h_deconv_concat = h_deconv
                deconv[layer] = h_deconv_concat
                print('h_deconv_concat',h_deconv_concat)

                if layer != 0:                
                    conv1 = atrous_conv2d(h_deconv_concat, features//2, kernel=3, rate=1, pad=0, pad_type='zero', scope='atrous1')
                    conv2 = atrous_conv2d(h_deconv_concat, features//2, kernel=3, rate=2, pad=0, pad_type='zero', scope='atrous2')
                    conv3 = atrous_conv2d(h_deconv_concat, features//2, kernel=3, rate=3, pad=0, pad_type='zero', scope='atrous3')
                #if layer == 0:                
                #    conv1 = atrous_conv2d(h_deconv_concat, features, kernel=features, rate=1, pad=0, pad_type='zero', scope='atrous1')
                #    conv2 = atrous_conv2d(h_deconv_concat, features, kernel=features, rate=2, pad=0, pad_type='zero', scope='atrous2')
                #    conv3 = atrous_conv2d(h_deconv_concat, features, kernel=features, rate=3, pad=0, pad_type='zero', scope='atrous3')
                    beta1 = tf.get_variable("GGammaalphabeta1", [1], initializer=tf.constant_initializer(1/3.0))
                    beta2 = tf.get_variable("GGammaalphabeta2", [1], initializer=tf.constant_initializer(1/3.0))
                    beta3 = tf.get_variable("GGammaalphabeta3", [1], initializer=tf.constant_initializer(1/3.0))
                    '''tf.summary.scalar("up_conv_%d" % layer + '/alphabeta1', beta1)
                    tf.summary.scalar("up_conv_%d" % layer + '/alphabeta2', beta2)
                    tf.summary.scalar("up_conv_%d" % layer + '/alphabeta3', beta3)'''
                    conv = beta1*conv1 + beta2*conv2 + beta3*conv3
                    conv = tf_contrib.layers.batch_norm(conv,decay=0.9, epsilon=1e-05,center=True, scale=True, updates_collections=None,is_training=trainable)
                    in_node = tf.nn.relu(conv)
                    up_h_convs[layer] = in_node
                    print('up_h_convs[layer]',up_h_convs[layer])
                    size *= 2
                    size -= 4

        # Output Map
        #with tf.variable_scope("output_map", reuse=reuse):
        weight = weight_variable([1, 1, features_root, n_class], stddev, weight_init, name = 'out_w')
        bias = bias_variable([n_class], weight_init, name="bias")
        conv = conv2d(in_node, weight, bias, tf.constant(1.0),reuse=reuse)
            #output_map = tf.nn.relu(conv)
        output_map = conv
        print(output_map)
        #up_h_convs["out"] = output_map

        '''if summaries:
            with tf.name_scope("summaries"):
                for i, (c1, c2) in enumerate(convs):
                    tf.summary.image('summary_conv_%02d_01' % i, get_image_summary(c1))
                    tf.summary.image('summary_conv_%02d_02' % i, get_image_summary(c2))

                for k in pools.keys():
                    tf.summary.image('summary_pool_%02d' % k, get_image_summary(pools[k]))

                for k in deconv.keys():
                    tf.summary.image('summary_deconv_concat_%02d' % k, get_image_summary(deconv[k]))

                ''''''for k in dw_h_convs.keys():
                    #tf.summary.histogram("dw_convolution_%02d" % k + '/activations', dw_h_convs[k])
                    tf.summary.scalar("down_conv_%d" % k + '/gamma1', gamma1)
                    tf.summary.scalar("down_conv_%d" % k + '/gamma2', gamma2)
                    tf.summary.scalar("down_conv_%d" % k + '/gamma3', gamma3)

                for k in up_h_convs.keys():
                    #tf.summary.histogram("up_convolution_%s" % k + '/activations', up_h_convs[k])
                    tf.summary.scalar("up_conv_%d" % k + '/alphabeta1', beta1)
                    tf.summary.scalar("up_conv_%d" % k + '/alphabeta2', beta2)
                    tf.summary.scalar("up_conv_%d" % k + '/alphabeta3', beta3)''''''
                tf.summary.image("out" , get_image_summary(tf.expand_dims(tf.argmax(output_map,-1),-1)))
                tf.summary.image("label" , get_image_summary(tf.expand_dims(tf.argmax(labels,-1),-1)))
                tf.summary.image("offset" , get_image_summary(offset1))
                tf.summary.image("input" , tf.expand_dims(x[0,:,:,:],0))'''

        variables = []
        for w1, w2 in weights:
            variables.append(w1)
            variables.append(w2)

        for b1, b2 in biases:
            variables.append(b1)
            variables.append(b2)
            
        end_points['Logits'] = output_map
        end_points['Predictions'] = layers.softmax(output_map, scope='predictions')

        return output_map,end_points
    
def get_image_summary(img, idx=0):
    """
    Make an image summary for 4d tensor image with index idx
    """

    V = tf.slice(img, (0, 0, 0, idx), (1, -1, -1, 1))
    V -= tf.reduce_min(V)
    V /= tf.reduce_max(V)
    V *= 255

    img_w = tf.shape(img)[1]
    img_h = tf.shape(img)[2]
    V = tf.reshape(V, tf.stack((img_w, img_h, 1)))
    V = tf.transpose(V, (2, 0, 1))
    V = tf.reshape(V, tf.stack((-1, img_w, img_h, 1)))
    return V
