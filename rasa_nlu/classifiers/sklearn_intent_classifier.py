import os

from rasa_nlu.components import Component
from rasa_nlu.training_data import TrainingData

# How many intents are at max put into the output intent ranking, everything else will be cut off
INTENT_RANKING_LENGTH = 10


class SklearnIntentClassifier(Component):
    """Intent classifier using the sklearn framework"""

    name = "intent_classifier_sklearn"

    context_provides = {
        "process": ["intent", "intent_ranking"],
    }

    output_provides = ["intent", "intent_ranking"]

    def __init__(self, clf=None, le=None):
        """Construct a new intent classifier using the sklearn framework."""

        if le is not None:
            self.le = le
        else:
            from sklearn.preprocessing import LabelEncoder
            self.le = LabelEncoder()
        self.clf = clf

    def transform_labels_str2num(self, labels):
        # type: ([str]) -> [int]
        """Transforms a list of strings into numeric label representation.

        :param labels: List of labels to convert to numeric representation"""

        return self.le.fit_transform(labels)

    def transform_labels_num2str(self, y):
        # type: ([int]) -> [str]
        """Transforms a list of strings into numeric label representation.

        :param y: List of labels to convert to numeric representation"""

        return self.le.inverse_transform(y)

    def train(self, training_data, intent_features, num_threads):
        # type: (TrainingData, [float], int) -> None
        """Train the intent classifier on a data set.

        :param num_threads: number of threads used during training time"""
        from sklearn.model_selection import GridSearchCV
        from sklearn.svm import SVC
        import numpy as np

        labels = [e["intent"] for e in training_data.intent_examples]

        if len(set(labels)) < 2:
            raise Exception("Can not train an intent classifier. Need at least 2 different classes.")
        y = self.transform_labels_str2num(labels)
        X = intent_features

        tuned_parameters = [{'C': [1, 2, 5, 10, 20, 100], 'kernel': ['linear']}]
        cv_splits = min(5, np.min(np.bincount(y)))
        self.clf = GridSearchCV(SVC(C=1, probability=True),
                                param_grid=tuned_parameters, n_jobs=num_threads,
                                cv=cv_splits, scoring='f1_weighted')

        self.clf.fit(X, y)

    def process(self, intent_features):
        # type: ([float]) -> dict
        """Returns the most likely intent and its probability for the input text."""

        X = intent_features.reshape(1, -1)
        intent_ids, probabilities = self.predict(X)
        intents = self.transform_labels_num2str(intent_ids)
        # `predict` returns a matrix as it is supposed to work for multiple examples as well, hence we need to flatten
        intents, probabilities = intents.flatten(), probabilities.flatten()
        if intents.size > 0 and probabilities.size > 0:
            ranking = zip(list(intents), list(probabilities))[:INTENT_RANKING_LENGTH]
            return {
                "intent": {
                    "name": intents[0],
                    "confidence": probabilities[0],
                },
                "intent_ranking": [{"name": intent, "confidence": score} for intent, score in ranking]
            }
        else:
            return {"intent": None, "intent_ranking": []}

    def predict_prob(self, X):
        # type: (np.ndarray) -> np.ndarray
        """Given a bow vector of an input text, predict the intent label. Returns probabilities for all labels.

        :param X: bow of input text
        :return: vector of probabilities containing one entry for each label"""

        import numpy as np

        return self.clf.predict_proba(X)

    def predict(self, X):
        """Given a bow vector of an input text, predict most probable label. Returns only the most likely label.

        :param X: bow of input text
        :return: tuple of first, the most probable label and second, its probability"""

        import numpy as np

        pred_result = self.predict_prob(X)
        # sort the probabilities retrieving the indices of the elements in sorted order
        sorted_indices = np.flip(np.argsort(pred_result, axis=1), axis=1)
        return sorted_indices, pred_result[:, sorted_indices]

    @classmethod
    def load(cls, model_dir, intent_classifier):
        # type: (str, str) -> SklearnIntentClassifier
        import cloudpickle

        if model_dir and intent_classifier:
            classifier_file = os.path.join(model_dir, intent_classifier)
            with open(classifier_file, 'rb') as f:
                return cloudpickle.load(f)
        else:
            return SklearnIntentClassifier()

    def persist(self, model_dir):
        # type: (str) -> dict
        """Persist this model into the passed directory. Returns the metadata necessary to load the model again."""

        import cloudpickle

        classifier_file = os.path.join(model_dir, "intent_classifier.pkl")
        with open(classifier_file, 'wb') as f:
            cloudpickle.dump(self, f)

        return {
            "intent_classifier": "intent_classifier.pkl"
        }
