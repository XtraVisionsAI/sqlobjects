# SQLObjects Development Rules

This directory contains comprehensive development rules and guidelines for the SQLObjects project, organized in a
hierarchical structure from general development practices to specific implementation details.

## Rules Structure Overview

### Layer 1: Universal Development Standards

**Rules that apply to any Python project, not specific to SQLObjects**

- **[00-development-workflow.md](00-development-workflow.md)** - Design-first development methodology
- **[01-development-standards.md](01-development-standards.md)** - Technical standards and tools

### Layer 2: SQLObjects Architecture Principles

**Core architectural decisions and design philosophy**

- **[02-architecture-principles.md](02-architecture-principles.md)** - Foundation technology and design priorities
- **[03-session-management-rules.md](03-session-management-rules.md)** - Session and transaction architecture

### Layer 3: SQLObjects Core Implementation

**Specific implementation rules for core functionality**

- **[04-model-system-rules.md](04-model-system-rules.md)** - Model definition and field system
- **[05-query-operation-rules.md](05-query-operation-rules.md)** - Query building and CRUD operations
- **[06-relationship-performance-rules.md](06-relationship-performance-rules.md)** - Relationships and performance
  optimization

### Layer 4: SQLObjects Extensions and Integration

**Advanced features and extension points**

- **[07-signal-extension-rules.md](07-signal-extension-rules.md)** - Signal system and extension architecture
- **[08-testing-principles-rules.md](08-testing-principles-rules.md)** - Testing philosophy and behavior verification
- **[09-documentation-consistency-rules.md](09-documentation-consistency-rules.md)** - Documentation accuracy and
  maintenance

## Current Rules Status

### Recently Updated (2024)

- **Removed unimplemented features**: File validators, window functions, query result caching
- **Confirmed expression syntax support**: User.field expressions fully supported
- **Updated feature boundaries**: Clear distinction between implemented and planned features
- **Added documentation consistency rules**: Ensure 100% accuracy between docs and code

### Implementation Status

- **✅ Fully Implemented**: Expression syntax, basic caching, bulk operations, signals, relationships
- **🚧 Planned Features**: Window functions (v2.0), advanced field optimization (v2.1), database health checks (v2.0)
- **❌ Not Planned**: File validators, complex monitoring (use external tools)

## Key Principles

### Design-First Development

**CRITICAL**: All code changes must begin with text-based design analysis

- Focus on "why" and "what" before "how"
- Architecture decisions over implementation details
- Behavior specifications over internal mechanisms

### Documentation-Code Consistency

**NEW**: All documentation must match actual implementation 100%

- No fictional features in documentation
- All API examples must be runnable code
- Feature status clearly marked (✅❌🚧📋)
- Regular audits to maintain accuracy

### Backward Compatibility

- Public APIs remain stable across minor versions
- 2-version deprecation cycle for breaking changes
- Migration tools and clear upgrade paths
- Feature flags for new functionality

### Performance Priority

- Built on SQLAlchemy Core for maximum performance
- Bulk operations for large datasets
- Memory-efficient patterns and optimization strategies
- Database-specific optimizations

### Type Safety and Developer Experience

- Comprehensive type annotations and validation
- Clear error messages and debugging support
- IDE integration and modern Python tooling
- Intuitive APIs with minimal boilerplate

## Development Workflow

### Before Making Changes

1. **Read relevant rules** - Understand current standards and constraints
2. **Design analysis** - Create text-based design document
3. **Impact assessment** - Evaluate effects on existing code and users
4. **Review process** - Get design feedback before implementation

### During Implementation

1. **Follow standards** - Adhere to coding style and organization rules
2. **Test comprehensively** - Unit, integration, and performance tests
3. **Document changes** - Update relevant documentation
4. **Validate design** - Ensure implementation matches design

### After Implementation

1. **Integration testing** - Verify compatibility with existing code
2. **Performance validation** - Benchmark critical operations
3. **Documentation updates** - Ensure all docs are current
4. **Migration guides** - Provide upgrade instructions if needed

## Rule Categories

### Development Process Rules

- **Workflow**: Design-first methodology and change management
- **Standards**: Code style, testing, and documentation requirements
- **Quality**: Review processes and validation requirements

### Architecture Rules

- **Principles**: Core design philosophy and technology choices
- **Boundaries**: Module responsibilities and integration patterns
- **Evolution**: How architecture can change while maintaining compatibility

### Implementation Rules

- **Models**: Field definitions, validation, and configuration
- **Queries**: Query building, execution, and optimization
- **Operations**: CRUD operations, bulk processing, and transactions
- **Relationships**: Loading strategies and performance optimization
- **Signals**: Lifecycle hooks and extension points

## Using These Rules

### For New Contributors

1. Start with **00-development-workflow.md** to understand the process
2. Read **01-development-standards.md** for technical requirements
3. Review **02-architecture-principles.md** for design philosophy
4. Study relevant implementation rules for your area of work

### For Feature Development

1. **Design Phase**: Follow workflow rules for design-first approach
2. **Architecture**: Ensure alignment with architectural principles
3. **Implementation**: Use developer guide for implementation patterns
4. **Testing**: Apply testing principles for behavior verification
5. **Integration**: Consider session management and performance principles

### For Bug Fixes

1. **Analysis**: Use workflow rules for problem reproduction and analysis
2. **Solution**: Design fix following relevant implementation rules
3. **Testing**: Apply testing standards and validation requirements
4. **Documentation**: Update rules if bug reveals missing guidance

### For Performance Optimization

1. **Measurement**: Follow performance monitoring guidelines
2. **Analysis**: Use relationship and query optimization rules
3. **Implementation**: Apply bulk operation and memory management patterns
4. **Validation**: Benchmark improvements and ensure no regressions

## Rule Maintenance

### When to Update Rules

- **New Features**: Add implementation rules for new functionality
- **Architecture Changes**: Update architectural principles and boundaries
- **Process Improvements**: Refine workflow and development standards
- **Lessons Learned**: Incorporate insights from development experience

### How to Update Rules

1. **Identify Gap**: Recognize missing or outdated guidance
2. **Design Update**: Plan rule changes following design-first approach
3. **Review Impact**: Assess effects on existing development practices
4. **Implement Changes**: Update relevant rule documents
5. **Communicate**: Notify team of rule changes and rationale

### Rule Consistency

- **Cross-References**: Ensure rules don't contradict each other
- **Completeness**: Cover all major development scenarios
- **Clarity**: Use clear, actionable language
- **Examples**: Provide concrete code examples where helpful

## Integration with Documentation

### Relationship to Other Docs

- **Rules** (this directory): Architectural principles and design guidelines
- **[Developer Guide](../docs/developer-guide.md)**: Implementation details and best practices
- **[Testing Principles](../tests/testing-principles.md)**: Testing philosophy and patterns
- **[Design Docs](../docs/design/)**: How SQLObjects works internally
- **[Feature Docs](../docs/features/)**: How to use SQLObjects functionality
- **API Docs**: Detailed interface specifications

### Documentation Philosophy

- **Rules**: Focus on "why" and architectural decisions
- **Developer Guide**: Focus on "how" and implementation patterns
- **Testing**: Focus on behavior verification over implementation testing
- **Progressive Complexity**: Simple concepts to advanced patterns
- **Practical Focus**: Real-world usage over theoretical completeness

## Compliance and Quality

### Rule Compliance

- All code changes must follow applicable rules
- Design documents required before implementation
- Code reviews verify rule adherence
- Automated checks where possible

### Quality Assurance

- **Testing**: Comprehensive test coverage requirements
- **Performance**: Benchmarking and optimization standards
- **Documentation**: Keep all docs synchronized with code
- **Compatibility**: Maintain backward compatibility standards

## Getting Help

### Understanding Rules

- Read the specific rule document for your area
- Check related architecture principles for context
- Review examples in feature documentation
- Ask for clarification if rules are unclear

### Proposing Changes

- Follow design-first workflow for rule changes
- Discuss architectural impacts with team
- Provide rationale and examples
- Consider effects on existing development practices