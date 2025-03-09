import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.decomposition import PCA
from scipy.sparse import hstack
import matplotlib.pyplot as plt
import numpy as np
import json

def run_event_clustering():
    try:
        with open("resource/cluster_config.json", "r", encoding="utf-8") as cfg:
            cluster_config = json.load(cfg)
        n_clusters = cluster_config.get("n_clusters", 3)
    except Exception:
        n_clusters = 3

    df = pd.read_csv('resource/zero_shot_results.csv')
    df.fillna('', inplace=True)
    df['classification_numeric'] = df['classification'].apply(lambda x: 1 if x == 'Important' else 0)
    encoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    selector_encoded = encoder.fit_transform(df[['type', 'name_role', 'selector']])
    tfidf = TfidfVectorizer(stop_words='english', max_features=100)
    page_title_features = tfidf.fit_transform(df['page_title'])
    scaler = StandardScaler()
    numeric_features = scaler.fit_transform(df[['confidence', 'classification_numeric']])
    features = hstack([page_title_features, numeric_features, selector_encoded])
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    kmeans.fit(features)
    df['cluster'] = kmeans.labels_
    # Save clustered results as CSV
    df[['url', 'selector', 'page_title', 'classification', 'confidence', 'cluster']].to_csv(
        'resource/clustered_output.csv', index=False)

    # Optionally, also save cluster centers in a separate file if needed
    with open('resource/cluster_centers.txt', 'w', encoding='utf-8') as f:
        f.write("Cluster Centers (Centroids):\n")
        f.write(str(kmeans.cluster_centers_))

    pca = PCA(n_components=2)
    principal_components = pca.fit_transform(features.toarray())
    df_pca = pd.DataFrame(data=principal_components, columns=['PC1', 'PC2'])
    plt.figure(figsize=(8, 6))
    plt.scatter(df_pca['PC1'], df_pca['PC2'], c=df['cluster'], cmap='viridis', alpha=0.7)
    plt.title('K-means Clustering - 2D PCA Projection')
    plt.xlabel('Principal Component 1')
    plt.ylabel('Principal Component 2')
    plt.colorbar(label='Cluster')
    plt.savefig('resource/clustered_plot.png')
    print(df[['url', 'selector', 'page_title', 'classification', 'confidence', 'cluster']])
    print("Cluster Centers (Centroids):")
    print(kmeans.cluster_centers_)

if __name__ == "__main__":
    run_event_clustering()