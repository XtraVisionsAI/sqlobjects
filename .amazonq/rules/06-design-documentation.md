# SQLObjects Design Documentation Standards

## Document Structure Standards

### 1. Standard Chapter Structure

All design documents must follow the following five-chapter structure:

```markdown
# [Module Name] Design Documentation

## Overview
## Core Features
## Module Architecture
## API Reference
## Usage Guide
```

### 2. Chapter Content Requirements

#### Overview Chapter

- Concisely explain module positioning and core value
- No more than 2-3 paragraphs
- Highlight the module's role in the entire system

#### Core Features Chapter

- List 3-4 core features
- Each feature includes brief description and code examples
- Code examples highlight the feature itself, avoid complex implementations

#### Module Architecture Chapter

- Core component list and brief descriptions
- Design philosophy of key classes/systems (not implementation details)
- Integration relationships with other modules
- Module responsibility separation explanation

#### API Reference Chapter

- Organize APIs by functional categories
- Include core methods and key parameters
- Concise code examples highlighting API usage
- Avoid detailed method signatures and implementation details

#### Usage Guide Chapter

- Clearly distinguish between basic usage and advanced usage
- Basic usage: simple and direct use cases
- Advanced usage: complex scenarios and best practices
- Progressive code examples, from simple to complex

## Code Example Standards

### 1. Code Style Requirements

```python
# ✅ Correct: Use English comments
User.name.upper()                    # Convert string to uppercase
User.age >= 18                       # Age filtering

# ❌ Incorrect: Use non-English comments
User.name.upper()                    # 字符串转大写
User.age >= 18                       # 年龄筛选
```

### 2. Example Complexity Control

```python
# ✅ Basic usage: Simple and direct
users = await User.objects.filter(User.is_active == True).all()

# ✅ Advanced usage: Moderately complex
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).select_related('profile').limit(10).all()

# ❌ Avoid: Overly complex examples
# Don't include lengthy business logic examples in documentation
```

### 3. Code Block Format

```python
# Each code block should have clear context
# Avoid isolated code fragments
# Ensure code can be understood independently

# Group related operations
query = User.objects.filter(User.is_active == True)
query = query.order_by(User.name)
users = await query.all()
```

## Content Organization Principles

### 1. Feature-Oriented

- Organize content around functionality
- Avoid focusing on implementation details
- Highlight use cases that users care about

### 2. Progressive Complexity

- Start with simple concepts
- Gradually introduce complex features
- Advanced usage builds upon basic usage

### 3. Practicality First

- Provide directly usable code examples
- Avoid purely theoretical explanations
- Each example has a clear use case

## Language and Style Requirements

### 1. Language Standards

- **Documentation Language**: English
- **Code Comments**: English
- **Variable Naming**: English (following Python conventions)

### 2. Writing Style

```markdown
# ✅ Correct: Concise and direct
Provides type-safe database expression support.

# ❌ Incorrect: Too verbose
This module, through a design based on SQLAlchemy's native expression system, provides developers with a complete, type-safe, high-performance database expression support solution.
```

### 3. Technical Terminology

- Use unified technical terminology across the project
- Briefly explain terms when they first appear
- Maintain consistency in terminology usage

## Module Integration Documentation Standards

### 1. Integration Relationship Description

```python
# ✅ Correct: Explain integration method and purpose
# fields module uses expressions module's function system
from .expressions import StringFunctionMixin

class EnhancedStringComparator(String.Comparator, StringFunctionMixin):
    """String comparator that inherits string functions from expressions module"""
    pass
```

### 2. Responsibility Separation Description

```markdown
- **module_a.py**: Responsible for Feature A, Feature B
- **module_b.py**: Responsible for Feature C, Feature D  
- **Integration Point**: Module collaboration through Interface X
```

## Version Control and Maintenance

### 1. Documentation Synchronization

- Design documents must stay synchronized with code implementation
- Update documentation when features change
- Regularly check documentation accuracy

### 2. Example Verification

- All code examples must be based on actual implementation
- Ensure example code runs correctly
- Avoid outdated or incorrect examples

### 3. Consistency Checks

- Regularly check consistency across multiple documents
- Unify terminology and concept usage
- Maintain consistent code style

## Quality Checklist

### Document Structure Check

- [ ] Follow standard five-chapter structure
- [ ] Chapter content is complete and balanced
- [ ] Logical flow is clear

### Content Quality Check

- [ ] Code examples use English comments
- [ ] Avoid overly complex examples
- [ ] Feature descriptions are concise and accurate

### Technical Accuracy Check

- [ ] Code examples based on latest implementation
- [ ] API descriptions match actual interfaces
- [ ] Module integration relationships are accurate

### User Experience Check

- [ ] Progressive learning path
- [ ] Practical code examples
- [ ] Clear usage guidance

## Documentation Template

```markdown
# SQLObjects [Module Name] Design Documentation

## Overview

[Module introduction, 2-3 paragraphs explaining module positioning and value]

## Core Features

### 1. [Feature Name]

[Feature description]

```python
# [Feature demonstration code]
```

### 2. [Feature Name]

[Feature description]

```python
# [Feature demonstration code]
```

### 3. [Feature Name]

[Feature description]

```python
# [Feature demonstration code]
```

## Module Architecture

### Core Components

- **Component A**: Function description
- **Component B**: Function description

### [Key System Name]

[System design philosophy and core class structure]

```python
# [Key class design example]
```

### Integration with Other Modules

#### Integration with [Module Name]

[Integration method and purpose description]

```python
# [Integration code example]
```

#### Module Responsibility Separation

- **module.py**: Responsible for function list
- **Integration Point**: Integration method description

## API Reference

### [API Category 1]

```python
# [Core API usage example]
```

### [API Category 2]

```python
# [Core API usage example]
```

## Usage Guide

### Basic Usage

```python
# [Simple use case]
```

### Advanced Usage

```python
# [Complex use cases and best practices]
```

```