"""Fit standardized RBF one-class boundaries and retain an independent nearest donor lookup."""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from .settings import FIELDS

MIN_DISTINCT_REFERENCE = 12


@dataclass
class Boundary:
    ids: list
    scaler: StandardScaler
    estimator: OneClassSVM
    donors: NearestNeighbors

    def score(self, rows):
        vectors = self.scaler.transform(matrix(rows))
        return -self.estimator.decision_function(vectors)

    def references(self, rows):
        vectors = self.scaler.transform(matrix(rows))
        distances, indices = self.donors.kneighbors(vectors)
        return [(float(gaps[0]), self.ids[positions[0]], len(positions))
                for gaps, positions in zip(distances, indices)]


def matrix(rows):
    return np.asarray([[row[field] for field in FIELDS] for row in rows], dtype=float)


def by_series(rows):
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda row: row['part_id']):
        groups[row['clip_variant']].append(row)
    return dict(groups)


def fit_models(rows, nu):
    models = {}
    for variant, samples in by_series(rows).items():
        points = matrix(samples)
        if len(np.unique(points, axis=0)) < MIN_DISTINCT_REFERENCE:
            continue
        scaler = StandardScaler().fit(points)
        scaled = scaler.transform(points)
        estimator = OneClassSVM(gamma='scale', nu=nu).fit(scaled)
        donors = NearestNeighbors(n_neighbors=3, algorithm='brute').fit(scaled)
        models[variant] = Boundary([row['part_id'] for row in samples], scaler, estimator, donors)
    if not models:
        raise ValueError(f'至少一个夹体版型需要 {MIN_DISTINCT_REFERENCE} 条不同参考读数')
    return models
