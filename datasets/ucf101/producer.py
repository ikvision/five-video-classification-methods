"""
Class for managing our data.
"""
import csv
import numpy as np
import random
import glob
import os.path
import sys
import operator
import threading
from utils.processor import process_image
from keras.utils import to_categorical
from config import config

class threadsafe_iterator:
    def __init__(self, iterator):
        self.iterator = iterator
        self.lock = threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self.lock:
            return next(self.iterator)

def threadsafe_generator(func):
    """Decorator"""
    def gen(*a, **kw):
        return threadsafe_iterator(func(*a, **kw))
    return gen

class DataSet():
    def __init__(self, seq_length, nb_classes, input_shape):
        self.seq_length = seq_length
        self.class_limit = nb_classes

        # TODO This shouldn't be hard coded
        self.max_frames = 300  # max number of frames a video can have for us to use it

        # Get the data.
        self.data = self.get_data()

        # Get the classes.
        self.classes = self.get_classes()

        # Now do some minor data cleaning.
        self.data = self.clean_data()

        self.image_shape = input_shape

    @staticmethod
    def get_data():
        """Load our data from file."""
        # TODO Path shouldn't be hard coded
        with open(os.path.join('datasets', 'ucf101', 'data_file.csv'), 'r') as fin:
            reader = csv.reader(fin)
            data = list(reader)

        return data

    def sample_filter(self, x):
        return int(x[3]) >= self.seq_length and int(x[3]) <= self.max_frames \
            and x[1] in self.classes

    def clean_data(self):
        """Limit samples to greater than the sequence length and fewer
        than N frames. Also limit it to classes we want to use."""
        return list(filter(self.sample_filter, self.data))

    def get_classes(self):
        """Extract the classes from our data. If we want to limit them,
        only return the classes we need."""
        classes = sorted(set([item[1] for item in self.data]))

        # Return.
        if self.class_limit is not None:
            return classes[:self.class_limit]
        else:
            return classes

    def get_class_one_hot(self, class_str):
        """Given a class as a string, return its number in the classes
        list. This lets us encode and one-hot it for training."""
        # Encode it first.
        label_encoded = self.classes.index(class_str)

        # Now one-hot it.
        label_hot = to_categorical(label_encoded, len(self.classes))

        assert len(label_hot) == len(self.classes)

        return label_hot

    def split_train_test(self):
        """Split the data into train and test groups."""
        # Two loops, only called twice and data is small.
        train = list(filter(lambda x: x[0] == 'train', self.data))
        test = list(filter(lambda x: x[0] == 'test', self.data))
        return train, test

    @threadsafe_generator
    def frame_generator(self, batch_size, train_test):
        """Return a generator that we can use to train on. There are
        a couple different things we can return:

        data_type: 'features', 'images'
        """
        # Get the right dataset for the generator.
        train, test = self.split_train_test()
        data = train if train_test == 'train' else test

        print("Creating %s generator with %d samples." % (train_test, len(data)))

        while 1:
            x = np.zeros((batch_size, self.seq_length, *self.image_shape))
            y = np.zeros((batch_size, len(self.classes)))
            samples = random.sample(data, batch_size)

            # Generate batch_size samples.
            for i, sample in enumerate(samples):
                # Get and resample frames.
                frames = self.get_frames_for_sample(sample)
                sampled_frames = self.rescale_list(frames, self.seq_length)

                # Build the image sequence
                sequence = self.build_image_sequence(sampled_frames)

                x[i] = np.array(sequence)
                y[i] = self.get_class_one_hot(sample[1])

            yield x, y

    def build_image_sequence(self, frames):
        """Given a set of frames (filenames), build our sequence."""
        return [process_image(x, self.image_shape) for x in frames]

    @staticmethod
    def get_frames_for_sample(sample):
        """Given a sample row from the data file, get all the corresponding frame
        filenames."""
        # TODO This shouldn't be hard coded
        path = os.path.join('datasets', 'ucf101', sample[0], sample[1], sample[2] + '*jpg')
        images = sorted(glob.glob(path))
        return images

    @staticmethod
    def rescale_list(input_list, size):
        """Given a list and a size, return a rescaled/samples list. For example,
        if we want a list of size 5 and we have a list of size 25, return a new
        list of size five which is every 5th element of the origina list."""
        assert len(input_list) >= size

        # Get the number to skip between iterations.
        skip = len(input_list) // size

        # Build our new output.
        output = [input_list[i] for i in range(0, len(input_list), skip)]

        # Cut off the last one if needed.
        return output[:size]

    @staticmethod
    def print_class_from_prediction(predictions, nb_to_return=5):
        """Given a prediction, print the top classes."""
        # Get the prediction for each label.
        label_predictions = {}
        for i, label in enumerate(data.classes):
            label_predictions[label] = predictions[i]

        # Now sort them.
        sorted_lps = sorted(
            label_predictions.items(),
            key=operator.itemgetter(1),
            reverse=True
        )

        # And return the top N.
        for i, class_prediction in enumerate(sorted_lps):
            if i > nb_to_return - 1 or class_prediction[1] == 0.0:
                break
            print("%s: %.2f" % (class_prediction[0], class_prediction[1]))