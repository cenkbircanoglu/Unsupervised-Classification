import json
import os

import numpy as np
import pandas as pd


def load_groundtruth(path):
    data = np.load(path, allow_pickle=True).item()
    orj_labels = []
    for i, labels in data.items():
        i = str(i)
        label = np.where(labels == 1)[0]
        orj_labels.append({'img_name': i, 'label': label})
    df = pd.DataFrame.from_records(orj_labels)
    return df


def calculate_accuracy(df, groundtruth_path, category_size=20, debug_root=None, epoch=None):
    label_df = load_groundtruth(groundtruth_path)
    df = pd.merge(df, label_df, on=['img_name'])
    exploded_df = df[['img_name', 'prediction', 'label']].explode('label')
    grouped_count_df = exploded_df.groupby(['prediction', 'label']).size().to_frame('size').reset_index()
    max_df = grouped_count_df.iloc[grouped_count_df.groupby('prediction')['size'].idxmax()]
    category_mapping = json.loads(max_df[['prediction', 'label']].to_json(orient='records'))
    acc = max_df['size'].sum() / len(exploded_df)
    informational_acc = (acc * max_df['label'].nunique() / category_size)
    print(acc, informational_acc)
    if debug_root:
        accuracy_path = os.path.join(debug_root, 'accuracy_%s.json' % epoch)
        df.to_json(accuracy_path, orient='records')
        mapping_path = os.path.join(debug_root, 'mapping_%s.json' % epoch)
        max_df[['prediction', 'label']].to_json(mapping_path, orient='records')

    return acc, informational_acc, df, category_mapping
