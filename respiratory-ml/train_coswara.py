import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
import joblib

# =========================
# 1. LOAD DATA
# =========================
df = pd.read_csv("dataset.csv", encoding="latin1", low_memory=False)

print("\nOriginal dataset shape:", df.shape)

# =========================
# 2. REMOVE MISSING LABELS
# =========================
df = df.dropna(subset=["COVID_test_status"])
df["COVID_test_status"] = df["COVID_test_status"].astype(int)

print("After removing missing labels:", len(df))
print("\nOriginal class distribution:")
print(df["COVID_test_status"].value_counts())

# =========================
# 3. SELECT FEATURES
# =========================
features = [
    "AGE",
    "GENDER",
    "Fever",
    "Cold",
    "Caugh",
    "Fatigue",
    "loss_of_smell",
    "Breathing_Difficulties",
    "Asthma",
    "Diabetes",
    "Hypertension",
    "Smoker"
]

df = df[features + ["COVID_test_status"]]

# =========================
# 4. ENCODE GENDER
# =========================
le = LabelEncoder()
df["GENDER"] = le.fit_transform(df["GENDER"].astype(str))

# =========================
# 5. SPLIT FEATURES + LABEL
# =========================
X = df.drop("COVID_test_status", axis=1)
y = df["COVID_test_status"]

# =========================
# 6. SMOTE BALANCING
# =========================
smote = SMOTE(random_state=42)
X_resampled, y_resampled = smote.fit_resample(X, y)

print("\nAfter SMOTE balancing:")
print(pd.Series(y_resampled).value_counts())

# =========================
# 7. TRAIN TEST SPLIT
# =========================
X_train, X_test, y_train, y_test = train_test_split(
    X_resampled,
    y_resampled,
    test_size=0.2,
    random_state=42,
    stratify=y_resampled
)

# =========================
# 8. SCALE FEATURES
# =========================
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_test = scaler.transform(X_test)

# =========================
# 9. TRAIN MODEL
# =========================
model = XGBClassifier(
    n_estimators=500,
    learning_rate=0.04,
    max_depth=7,
    subsample=0.9,
    colsample_bytree=0.9,
    random_state=42,
    n_jobs=-1,
    eval_metric="logloss"
)

print("\nTraining model...")
model.fit(X_train, y_train)

# =========================
# 10. EVALUATE
# =========================
pred = model.predict(X_test)

print("\nSMOTE Model Classification Report:\n")
print(classification_report(y_test, pred))

# =========================
# 11. SAVE FILES
# =========================
joblib.dump(model, "covid_model2.pkl")
joblib.dump(scaler, "scaler2.pkl")
joblib.dump(le, "gender_encoder2.pkl")

print("\n✅ Model + scaler + encoder saved successfully!")