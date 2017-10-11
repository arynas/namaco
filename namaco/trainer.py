import os

from keras.optimizers import Adam

from namaco.data.metrics import get_callbacks
from namaco.data.reader import batch_iter
from namaco.models import CharacterNER


class Trainer(object):

    def __init__(self,
                 model_config,
                 training_config,
                 checkpoint_path='',
                 save_path='',
                 tensorboard=True,
                 preprocessor=None,
                 ):

        self.model_config = model_config
        self.training_config = training_config
        self.checkpoint_path = checkpoint_path
        self.save_path = save_path
        self.tensorboard = tensorboard
        self.preprocessor = preprocessor

    def train(self, x_train, y_train, x_valid=None, y_valid=None):

        # Prepare training and validation data(steps, generator)
        train_steps, train_batches = batch_iter(
            x_train, y_train, self.training_config.batch_size, preprocessor=self.preprocessor)
        valid_steps, valid_batches = batch_iter(
            x_valid, y_valid, self.training_config.batch_size, preprocessor=self.preprocessor)

        # Build the model
        model = CharacterNER(self.model_config, len(self.preprocessor.vocab_tag))
        model.compile(loss=model.crf.loss,
                      optimizer=Adam(lr=self.training_config.learning_rate),
                      )

        # Prepare callbacks for training
        callbacks = get_callbacks(log_dir=self.checkpoint_path,
                                  tensorboard=self.tensorboard,
                                  eary_stopping=self.training_config.early_stopping,
                                  valid=(valid_steps, valid_batches, self.preprocessor))

        # Train the model
        model.fit_generator(generator=train_batches,
                            steps_per_epoch=train_steps,
                            epochs=self.training_config.max_epoch,
                            callbacks=callbacks)

        # Save the model
        model.save(os.path.join(self.save_path, 'model.h5'))
