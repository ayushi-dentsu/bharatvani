# Design Document - BharatVani

## Overview

BharatVani is an AI-powered voice health screening system designed to provide accessible healthcare screening for rural India through phone-based interactions. The system leverages voice biomarker analysis to assess respiratory health risk using a combination of AWS cloud services and serverless machine learning.

**Important Medical Disclaimer:** BharatVani provides preliminary health risk screening only. It does not diagnose medical conditions. All results require professional medical evaluation and confirmation by qualified healthcare providers.

The MVP focuses on demonstrating core functionality: voice collection via Amazon Connect IVR, respiratory health assessment through cough analysis using Lambda-based ML inference, and results delivery via SMS. The architecture is designed to be cost-effective and scalable, utilizing serverless technologies for optimal resource utilization and minimal operational overhead.

### Key Design Principles

1. **Accessibility First**: Phone-based interaction requiring no smartphone or internet access for users
2. **Serverless Architecture**: Lambda-based processing for automatic scaling and cost optimization
3. **Privacy by Design**: Encryption at rest and in transit, automatic data deletion, minimal data retention
4. **Cost Optimization**: Pay-per-use serverless services with no minimum charges
5. **Clinical Validation Ready**: Data collection and analysis pipeline designed for future clinical studies

## Architecture

### High-Level System Architecture

The BharatVani system utilizes a serverless architecture built on AWS Lambda functions for optimal cost efficiency and automatic scaling. The system processes voice calls through Amazon Connect, analyzes audio using Lambda-based ML inference, and delivers results via SMS.

**Key Architecture Benefits:**
- **Cost Optimization**: Pay-per-execution model with no minimum charges
- **Automatic Scaling**: Scales from 0 to 1000+ concurrent requests
- **Simplified Operations**: No server management or capacity planning
- **Fast Deployment**: Deploy and update functions in minutes

![Lambda Architecture](../generated-diagrams/bharatvani_lambda_architecture.png)

### Serverless Processing Pipeline

1. **Voice Collection**: Amazon Connect handles IVR interactions and audio recording
2. **Audio Processing**: Lambda function processes and validates audio quality using librosa
3. **Feature Extraction**: Extract MFCC and spectral features optimized for lightweight ML models
4. **Health Assessment**: Lambda-based ML inference performs respiratory health classification
5. **Results Processing**: Lambda function generates recommendations and prepares SMS content
6. **Results Delivery**: SMS notifications sent via Amazon SNS with health recommendations
7. **Data Management**: User records stored in DynamoDB, audio files in S3 with lifecycle policies

![User Journey](../generated-diagrams/bharatvani_lambda_user_journey.png)

## Components and Interfaces

### Amazon Connect IVR Interface

**Purpose**: Handles phone-based user interactions and audio collection

**Key Features**:
- Multi-language support (English, Hindi for MVP)
- Guided audio collection workflow
- 16kHz audio quality with automatic recording
- Error handling and retry mechanisms

**Interface Specification**:
```
Input: Incoming phone call
Output: Recorded audio file (WAV format, 16kHz, mono)
Data Flow: User → IVR Prompts → Audio Recording → S3 Storage
```

**IVR Flow Design**:
1. Welcome message and language selection
2. User information collection (name, age, phone number)
3. Health screening instructions
4. Guided cough collection (3 coughs with 2-second pauses)
5. Confirmation and next steps explanation

### Audio Processing Service

**Purpose**: Validates, processes, and extracts features from recorded audio

**Technology Stack**:
- AWS Lambda (Python 3.9 runtime)
- Librosa library for audio processing
- NumPy for numerical computations

**Processing Pipeline**:
```python
# Pseudo-code for audio processing
def process_audio(audio_file_path):
    # Load audio with librosa
    y, sr = librosa.load(audio_file_path, sr=16000)
    
    # Quality validation
    if len(y) < 30 * sr or len(y) > 60 * sr:
        raise AudioQualityError("Invalid duration")
    
    # Feature extraction
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
    zero_crossing_rate = librosa.feature.zero_crossing_rate(y)
    
    # Aggregate features
    features = {
        'mfcc_mean': np.mean(mfccs, axis=1),
        'mfcc_std': np.std(mfccs, axis=1),
        'spectral_centroid_mean': np.mean(spectral_centroids),
        'zcr_mean': np.mean(zero_crossing_rate)
    }
    
    return features
```

### Machine Learning Engine

**Purpose**: Performs respiratory health risk assessment using voice biomarkers via serverless Lambda functions

**Model Architecture**:
- Lightweight classification model optimized for Lambda deployment
- Binary classification: High Risk / Low Risk
- Confidence scoring for result reliability
- Model size: <50MB for optimal Lambda performance

**Lambda Configuration**:
```json
{
    "FunctionName": "bharatvani-respiratory-classifier",
    "Runtime": "python3.9",
    "MemorySize": 1024,
    "Timeout": 30,
    "Environment": {
        "MODEL_BUCKET": "bharatvani-models",
        "MODEL_KEY": "respiratory_model.pkl"
    }
}
```

**Input/Output Specification**:
```
Input: Feature vector (39 dimensions)
- MFCC coefficients (13 mean + 13 std)
- Spectral features (5 dimensions)
- Temporal features (8 dimensions)

Output: Risk assessment
- risk_level: "HIGH" | "LOW"
- confidence_score: 0.0 to 1.0
- recommendations: Array of strings
- processing_time: Execution duration
```

### Results Delivery System

**Purpose**: Delivers screening results and recommendations via SMS

**SMS Template Design**:
```
BharatVani Health Screening Results:
Risk Level: {risk_level}
Confidence: {confidence_score}%

{recommendations}

For questions, call: 1800-XXX-XXXX
```

**Multi-language Support**:
- Template localization for Hindi and English
- Cultural adaptation of health messaging
- Emergency contact information in local language

### Demo Dashboard Interface

**Purpose**: Real-time visualization for hackathon demonstration

**Technology Stack**:
- React.js frontend with real-time updates
- WebSocket connection for live data streaming
- Chart.js for audio waveform visualization

**Dashboard Components**:
1. **Live Audio Visualization**: Real-time waveform display during calls
2. **Feature Analysis**: Visual representation of extracted MFCC features
3. **ML Predictions**: Live display of model outputs and confidence scores
4. **System Metrics**: Call volume, success rates, geographic distribution
5. **Sample Playback**: Anonymized audio samples for demonstration

## Data Models

### User Health Record

```json
{
    "user_id": "string (UUID)",
    "phone_number": "string (hashed)",
    "name": "string (encrypted)",
    "age": "number",
    "language_preference": "string",
    "screening_timestamp": "ISO 8601 datetime",
    "audio_file_s3_key": "string",
    "extracted_features": {
        "mfcc_features": "array[26]",
        "spectral_features": "array[5]",
        "temporal_features": "array[8]"
    },
    "ml_results": {
        "risk_level": "HIGH | LOW",
        "confidence_score": "number (0-1)",
        "model_version": "string",
        "processing_timestamp": "ISO 8601 datetime"
    },
    "sms_delivery": {
        "sent_timestamp": "ISO 8601 datetime",
        "delivery_status": "SENT | DELIVERED | FAILED",
        "retry_count": "number"
    },
    "data_retention": {
        "created_at": "ISO 8601 datetime",
        "expires_at": "ISO 8601 datetime (30 days)"
    }
}
```

### Audio File Metadata

```json
{
    "file_id": "string (UUID)",
    "s3_bucket": "string",
    "s3_key": "string",
    "file_size_bytes": "number",
    "duration_seconds": "number",
    "sample_rate": "number (16000)",
    "format": "string (WAV)",
    "quality_metrics": {
        "signal_to_noise_ratio": "number",
        "clipping_detected": "boolean",
        "silence_percentage": "number"
    },
    "processing_status": "PENDING | PROCESSED | FAILED",
    "encryption_key_id": "string"
}
```

### System Analytics

```json
{
    "analytics_id": "string (UUID)",
    "date": "ISO 8601 date",
    "metrics": {
        "total_calls": "number",
        "successful_screenings": "number",
        "failed_screenings": "number",
        "average_call_duration": "number (seconds)",
        "high_risk_detections": "number",
        "sms_delivery_rate": "number (percentage)"
    },
    "geographic_distribution": {
        "state_wise_counts": "object",
        "language_preference_counts": "object"
    },
    "system_performance": {
        "average_processing_time": "number (seconds)",
        "ml_model_accuracy": "number (percentage)",
        "cost_per_screening": "number (INR)"
    }
}
```

Now I need to use the prework tool to analyze the acceptance criteria before writing the Correctness Properties section:

<function_calls>
<invoke name="prework">
<parameter name="featureName">bharatvani

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis of acceptance criteria, the following properties ensure system correctness across all inputs and scenarios:

### Property 1: User Data Collection Completeness
*For any* voice screening session, when user information is collected, all required fields (name, age, phone number) should be captured and stored in the Health_Record
**Validates: Requirements 1.3**

### Property 2: Audio Quality Validation
*For any* audio recording received from IVR, the Audio_Processor should validate duration (30-60 seconds) and sampling rate (minimum 8kHz), rejecting recordings that don't meet quality standards
**Validates: Requirements 1.5, 2.1, 2.4**

### Property 3: Feature Extraction Consistency
*For any* valid audio input, the Audio_Processor should extract the complete feature set (MFCC, spectral, temporal features) required for ML analysis
**Validates: Requirements 2.3**

### Property 4: Data Encryption Compliance
*For any* user data or audio file stored in the system, it should be encrypted both in transit and at rest with appropriate encryption keys
**Validates: Requirements 2.2, 2.6, 7.1**

### Property 5: ML Output Format Consistency
*For any* feature vector processed by the ML_Engine, the output should contain risk_level (HIGH/LOW), confidence_score (0-1), and recommendations array
**Validates: Requirements 3.1, 3.2**

### Property 6: Confidence Threshold Handling
*For any* ML prediction with confidence below 60%, the system should flag the result as inconclusive and recommend re-screening
**Validates: Requirements 3.3**

### Property 7: Risk-Based Recommendation Generation
*For any* ML prediction result, the system should generate appropriate recommendations based on risk level (emergency contacts for high risk, preventive tips for low risk)
**Validates: Requirements 3.4, 4.3, 4.4**

### Property 8: Processing Time Limits
*For any* audio feature extraction and ML analysis, the complete processing should finish within 30 seconds of receiving the audio
**Validates: Requirements 3.5**

### Property 9: SMS Content Completeness
*For any* screening result sent via SMS, the message should include risk level, confidence score, next steps, and be delivered in the user's selected language
**Validates: Requirements 4.2, 8.3**

### Property 10: SMS Delivery Timing
*For any* completed ML analysis, the SMS notification should be sent within 2 minutes of analysis completion
**Validates: Requirements 4.1**

### Property 11: SMS Retry Logic
*For any* failed SMS delivery, the system should retry up to 3 times with exponential backoff before marking as completely failed
**Validates: Requirements 4.5**

### Property 12: Dashboard Real-Time Updates
*For any* new screening data, the Demo_Dashboard should automatically update without manual refresh to display the latest information
**Validates: Requirements 5.4**

### Property 13: End-to-End Timing
*For any* complete screening workflow (call initiation to SMS delivery), the total time should not exceed 5 minutes under normal operating conditions
**Validates: Requirements 6.6**

### Property 14: Comprehensive Error Logging
*For any* system error or failure, detailed error information should be logged with timestamp, component, and context for debugging purposes
**Validates: Requirements 3.6, 4.6, 6.5**

### Property 15: Language Preference Consistency
*For any* screening session, the user's language preference should be maintained consistently across IVR prompts, SMS messages, and stored preferences
**Validates: Requirements 8.4**

### Property 16: Language Fallback Behavior
*For any* language detection failure or invalid language input, the system should default to Hindi and provide language selection options
**Validates: Requirements 8.6**

### Property 17: Access Control Enforcement
*For any* attempt to access Health_Records, the system should verify authorization and block unauthorized access attempts
**Validates: Requirements 7.2**

### Property 18: Data Anonymization
*For any* completed screening data used for system improvement, personal identifiers should be automatically removed while preserving analytical value
**Validates: Requirements 7.3**

### Property 19: Data Deletion Compliance
*For any* user data deletion request, all personal information should be removed from all system components within 24 hours
**Validates: Requirements 7.5**

### Property 20: Audit Trail Completeness
*For any* data access or modification operation, an audit log entry should be created with timestamp, user, action, and affected data
**Validates: Requirements 7.6**

### Property 21: Schema Compatibility
*For any* health data stored in the system, it should follow standardized formats compatible with future ABDM integration requirements
**Validates: Requirements 9.3, 9.4**

### Property 22: API Availability
*For any* REST API endpoint defined for future integrations, it should be accessible and return appropriate responses for valid requests
**Validates: Requirements 9.6**

### Property 23: Cost Tracking Accuracy
*For any* screening processed by the system, cost metrics should be accurately collected and associated with the screening for monitoring purposes
**Validates: Requirements 10.1**

### Property 24: Audio Compression Quality
*For any* audio file compressed for storage efficiency, the compressed version should maintain sufficient quality for accurate ML analysis
**Validates: Requirements 10.4**

### Property 25: Data Lifecycle Management
*For any* audio file or user record, it should be automatically deleted after 30 days to comply with privacy requirements
**Validates: Requirements 2.5**

## Error Handling

### Error Classification and Response Strategy

**Audio Quality Errors**:
- Invalid duration (< 30s or > 60s): Request re-recording with specific guidance
- Poor signal quality: Provide audio quality tips and retry
- Format incompatibility: Convert automatically or request re-recording

**ML Processing Errors**:
- Feature extraction failure: Log error, use fallback feature set
- Model inference timeout: Retry with reduced feature set, escalate if persistent
- Low confidence predictions: Flag as inconclusive, recommend re-screening

**Communication Errors**:
- SMS delivery failure: Implement exponential backoff retry (3 attempts)
- IVR connection issues: Provide alternative contact methods
- Network timeouts: Graceful degradation with offline capability

**Data Security Errors**:
- Encryption failures: Halt processing, alert security team
- Access control violations: Log incident, block access, notify administrators
- Data corruption: Restore from backup, investigate root cause

### Fallback Mechanisms

1. **ML Model Fallback**: If primary model fails, use simplified rule-based assessment
2. **Language Fallback**: Default to Hindi if language detection fails
3. **Communication Fallback**: Store results for later delivery if SMS fails completely
4. **Storage Fallback**: Use alternative storage regions if primary fails

## Testing Strategy

### Dual Testing Approach

The BharatVani system requires comprehensive testing using both unit tests and property-based tests to ensure correctness across all scenarios:

**Unit Tests**: Focus on specific examples, edge cases, and integration points
- IVR flow testing with sample audio files
- SMS template validation with different risk levels
- Dashboard component rendering with mock data
- Error condition handling with invalid inputs

**Property-Based Tests**: Verify universal properties across all possible inputs
- Audio processing with randomly generated audio characteristics
- ML model behavior with various feature combinations
- SMS delivery with different user preferences and network conditions
- Data encryption and access control with various user roles

### Property-Based Testing Configuration

**Testing Framework**: Hypothesis (Python) for Lambda functions, fast-check (JavaScript) for dashboard
**Test Iterations**: Minimum 100 iterations per property test to ensure comprehensive coverage
**Test Tagging**: Each property test tagged with format: **Feature: bharatvani, Property {number}: {property_text}**

### Example Property Test Structure

```python
from hypothesis import given, strategies as st
import pytest

@given(
    audio_duration=st.floats(min_value=0, max_value=120),
    sample_rate=st.integers(min_value=1000, max_value=48000),
    audio_quality=st.floats(min_value=0, max_value=1)
)
def test_audio_quality_validation_property(audio_duration, sample_rate, audio_quality):
    """
    Feature: bharatvani, Property 2: Audio Quality Validation
    For any audio recording, validation should correctly accept/reject based on quality standards
    """
    result = audio_processor.validate_audio(audio_duration, sample_rate, audio_quality)
    
    # Property: Valid audio (30-60s, >=8kHz, good quality) should be accepted
    if 30 <= audio_duration <= 60 and sample_rate >= 8000 and audio_quality > 0.5:
        assert result.is_valid == True
    else:
        assert result.is_valid == False
        assert len(result.error_messages) > 0
```

### Integration Testing Strategy

1. **End-to-End Workflow Testing**: Complete user journey from call to SMS delivery
2. **AWS Service Integration**: Test all AWS service interactions with real services
3. **Load Testing**: Verify system behavior under concurrent user load
4. **Security Testing**: Penetration testing for data protection and access controls
5. **Multi-language Testing**: Verify functionality across supported languages

### Performance Testing Requirements

- **Response Time**: IVR response < 3 seconds, ML processing < 30 seconds
- **Throughput**: Support 100 concurrent calls during peak demonstration
- **Scalability**: Auto-scaling verification under increasing load
- **Resource Utilization**: Monitor AWS costs and optimize resource usage

### Clinical Validation Preparation

While not part of the hackathon MVP, the testing strategy prepares for future clinical validation:

- **Data Collection Standards**: Ensure collected data meets clinical research requirements
- **Accuracy Metrics**: Track sensitivity, specificity, and predictive values
- **Bias Detection**: Monitor for demographic or linguistic biases in predictions
- **Regulatory Compliance**: Prepare for medical device validation requirements

## Future Scalability Considerations

### Multi-Language Expansion

The current architecture supports easy addition of new languages through:
- Modular IVR prompt management in S3
- Language-specific SMS templates in DynamoDB
- Configurable language detection and routing

### Additional Health Conditions

The ML pipeline is designed for extensibility:
- Modular feature extraction supporting different biomarkers
- Multi-Lambda deployment for different health conditions
- Configurable risk assessment workflows

### Healthcare System Integration

Prepared for integration with Indian healthcare infrastructure:
- ABDM-compatible data schemas and APIs
- FHIR-compliant health record formats
- Integration points for PHC and ASHA worker systems

### Scale and Performance Optimization

Architecture supports scaling to millions of users:
- Serverless components with automatic scaling
- CDN distribution for global audio processing
- Database sharding strategies for large-scale data storage
- Cost optimization through reserved capacity and spot instances