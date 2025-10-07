# train_model.py
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
import joblib

DATA_PATH = os.path.join("datasets", "Amazon_Labeled_Reviews.csv")

# Try reading csv with utf-8 then fallback
try:
    df = pd.read_csv(DATA_PATH)
except UnicodeDecodeError:
    df = pd.read_csv(DATA_PATH, encoding='latin1')

print("Columns:", list(df.columns))

# detect text column
possible_text_cols = ['review','text','reviewText','review_body','content','review_text']
text_col = next((c for c in possible_text_cols if c in df.columns), None)
if text_col is None:
    # fallback: choose first column that looks like string
    text_col = df.select_dtypes(include=['object']).columns[0]
print("Using text column:", text_col)

# detect label column
possible_label_cols = ['label','class','target','is_fake','fake','labelled']
label_col = next((c for c in possible_label_cols if c in df.columns), None)
if label_col is None:
    # fallback: pick a column that is not the text column and likely small-cardinality
    candidates = [c for c in df.columns if c != text_col]
    label_col = candidates[-1]
print("Using label column:", label_col)

# Prepare X and y
X = df[text_col].astype(str).fillna(" ")
y = df[label_col]

# Normalize/encode labels if necessary
if y.dtype == object or y.dtype.name == 'category':
    y_str = y.astype(str).str.lower()
    if set(y_str.unique()) <= {'fake','real'}:
        y = y_str.map({'real': 1, 'fake': 0})
    else:
        le = LabelEncoder()
        y = le.fit_transform(y)
        joblib.dump(le, "label_encoder.pkl")
else:
    # ensure numeric
    y = y.astype(int)

print("Label distribution:\n", pd.Series(y).value_counts())

# train/test split (stratify if possible)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Vectorize
vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
X_train_tfidf = vectorizer.fit_transform(X_train)
X_test_tfidf = vectorizer.transform(X_test)

# Train model
model = LogisticRegression(max_iter=1000, solver='liblinear')
model.fit(X_train_tfidf, y_train)

# Evaluate
acc = model.score(X_test_tfidf, y_test)
print(f"Test accuracy: {acc:.4f}")

# Save artifacts
os.makedirs("fake_review_models", exist_ok=True)
joblib.dump(model, "fake_review_models/fake_review_model.pkl")
joblib.dump(vectorizer, "fake_review_models/tfidf_vectorizer.pkl")
print("Saved model and vectorizer to models/")
