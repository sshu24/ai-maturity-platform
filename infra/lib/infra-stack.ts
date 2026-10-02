import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ----------------------------------------------------------------
    // VPC
    // ----------------------------------------------------------------
    const vpc = new ec2.Vpc(this, 'AiMaturityVpc', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      ],
    });

    // ----------------------------------------------------------------
    // Security Groups
    // ----------------------------------------------------------------
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DbSecurityGroup', {
      vpc,
      description: 'Security group for RDS PostgreSQL',
      allowAllOutbound: false,
    });

    const ecsSecurityGroup = new ec2.SecurityGroup(this, 'EcsSecurityGroup', {
      vpc,
      description: 'Security group for ECS tasks',
      allowAllOutbound: true,
    });

    const albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc,
      description: 'Security group for ALB',
      allowAllOutbound: true,
    });

    // Allow ALB to reach ECS
    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80));
    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443));

    // Allow ECS to reach RDS
    dbSecurityGroup.addIngressRule(
      ecsSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow ECS to connect to RDS'
    );

    // Allow ALB to reach ECS services
    ecsSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(8000));
    ecsSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(8501));

    // ----------------------------------------------------------------
    // Secrets Manager — DB credentials
    // ----------------------------------------------------------------
    const dbSecret = new secretsmanager.Secret(this, 'DbSecret', {
      secretName: 'ai-maturity/db-credentials',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'projecta' }),
        generateStringKey: 'password',
        excludePunctuation: true,
        includeSpace: false,
      },
    });

    const appSecret = new secretsmanager.Secret(this, 'AppSecret', {
      secretName: 'ai-maturity/app-secrets',
      secretObjectValue: {
        SECRET_KEY: cdk.SecretValue.unsafePlainText('REPLACE_WITH_OPENSSL_RAND_HEX_32'),
        ANTHROPIC_API_KEY: cdk.SecretValue.unsafePlainText('REPLACE_WITH_YOUR_KEY'),
        OPENAI_API_KEY: cdk.SecretValue.unsafePlainText('REPLACE_WITH_YOUR_KEY'),
        LANGCHAIN_API_KEY: cdk.SecretValue.unsafePlainText('REPLACE_WITH_YOUR_KEY'),
      },
    });

    // ----------------------------------------------------------------
    // RDS PostgreSQL
    // ----------------------------------------------------------------
    const dbInstance = new rds.DatabaseInstance(this, 'AiMaturityDb', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSecurityGroup],
      credentials: rds.Credentials.fromSecret(dbSecret),
      databaseName: 'projecta_db',
      allocatedStorage: 20,
      maxAllocatedStorage: 100,
      deletionProtection: false,       // set true for production
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      backupRetention: cdk.Duration.days(7),
      multiAz: false,                  // set true for production
    });

    // ----------------------------------------------------------------
    // ECR Repositories
    // ----------------------------------------------------------------
    const fastapiRepo = ecr.Repository.fromRepositoryName(
      this, 'FastApiRepo', 'ai-maturity-fastapi'
    );

    const streamlitRepo = ecr.Repository.fromRepositoryName(
      this, 'StreamlitRepo', 'ai-maturity-streamlit'
    );

    // ----------------------------------------------------------------
    // ECS Cluster
    // ----------------------------------------------------------------
    const cluster = new ecs.Cluster(this, 'AiMaturityCluster', {
      vpc,
      clusterName: 'ai-maturity-cluster',
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
    });

    // ----------------------------------------------------------------
    // IAM Task Execution Role
    // ----------------------------------------------------------------
    const taskExecutionRole = new iam.Role(this, 'TaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AmazonECSTaskExecutionRolePolicy'
        ),
      ],
    });

    // Task Role (separate from execution role) — for SSM exec
    const taskRole = new iam.Role(this, 'TaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inlinePolicies: {
        SSMExec: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                'ssmmessages:CreateControlChannel',
                'ssmmessages:CreateDataChannel',
                'ssmmessages:OpenControlChannel',
                'ssmmessages:OpenDataChannel',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });

    // Allow tasks to read secrets
    dbSecret.grantRead(taskExecutionRole);
    appSecret.grantRead(taskExecutionRole);

    // ----------------------------------------------------------------
    // FastAPI Task Definition
    // ----------------------------------------------------------------
    const fastapiTaskDef = new ecs.FargateTaskDefinition(this, 'FastApiTaskDef', {
      memoryLimitMiB: 512,
      cpu: 256,
      executionRole: taskExecutionRole,
      taskRole: taskRole,  
    });

    const fastapiLogGroup = new logs.LogGroup(this, 'FastApiLogGroup', {
      logGroupName: '/ecs/ai-maturity-fastapi',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    fastapiTaskDef.addContainer('FastApiContainer', {
      image: ecs.ContainerImage.fromEcrRepository(fastapiRepo, 'latest'),
      portMappings: [{ containerPort: 8000 }],
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'fastapi',
        logGroup: fastapiLogGroup,
      }),
      environment: {
        ENV: 'production',
        POSTGRES_HOST: dbInstance.instanceEndpoint.hostname,
        POSTGRES_PORT: '5432',
        POSTGRES_DB: 'projecta_db',
        ALGORITHM: 'HS256',
        ACCESS_TOKEN_EXPIRE_MINUTES: '480',
        LANGCHAIN_TRACING_V2: 'true',
        LANGCHAIN_PROJECT: 'ai-maturity-platform',
      },
      secrets: {
        POSTGRES_USER: ecs.Secret.fromSecretsManager(dbSecret, 'username'),
        POSTGRES_PASSWORD: ecs.Secret.fromSecretsManager(dbSecret, 'password'),
        SECRET_KEY: ecs.Secret.fromSecretsManager(appSecret, 'SECRET_KEY'),
        ANTHROPIC_API_KEY: ecs.Secret.fromSecretsManager(appSecret, 'ANTHROPIC_API_KEY'),
        OPENAI_API_KEY: ecs.Secret.fromSecretsManager(appSecret, 'OPENAI_API_KEY'),
        LANGCHAIN_API_KEY: ecs.Secret.fromSecretsManager(appSecret, 'LANGCHAIN_API_KEY'),
      },
    });

    // ----------------------------------------------------------------
    // Streamlit Task Definition
    // ----------------------------------------------------------------
    const streamlitTaskDef = new ecs.FargateTaskDefinition(this, 'StreamlitTaskDef', {
      memoryLimitMiB: 512,
      cpu: 256,
      executionRole: taskExecutionRole,
      taskRole: taskRole,
    });

    const streamlitLogGroup = new logs.LogGroup(this, 'StreamlitLogGroup', {
      logGroupName: '/ecs/ai-maturity-streamlit',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    streamlitTaskDef.addContainer('StreamlitContainer', {
      image: ecs.ContainerImage.fromEcrRepository(streamlitRepo, 'latest'),
      portMappings: [{ containerPort: 8501 }],
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'streamlit',
        logGroup: streamlitLogGroup,
      }),
      environment: {
        FASTAPI_BASE_URL: 'http://ai-maturity-alb-401606835.us-west-1.elb.amazonaws.com',
      },
    });

    // ----------------------------------------------------------------
    // Application Load Balancer
    // ----------------------------------------------------------------
    const alb = new elbv2.ApplicationLoadBalancer(this, 'AiMaturityAlb', {
      vpc,
      internetFacing: true,
      securityGroup: albSecurityGroup,
      loadBalancerName: 'ai-maturity-alb',
      idleTimeout: cdk.Duration.seconds(120),
    });

    // ----------------------------------------------------------------
    // FastAPI ECS Service
    // ----------------------------------------------------------------
    const fastapiService = new ecs.FargateService(this, 'FastApiService', {
      cluster,
      taskDefinition: fastapiTaskDef,
      desiredCount: 1,
      securityGroups: [ecsSecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serviceName: 'fastapi-service',
      assignPublicIp: false,
    });

    // ----------------------------------------------------------------
    // Streamlit ECS Service
    // ----------------------------------------------------------------
    const streamlitService = new ecs.FargateService(this, 'StreamlitService', {
      cluster,
      taskDefinition: streamlitTaskDef,
      desiredCount: 1,
      securityGroups: [ecsSecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serviceName: 'streamlit-service',
      assignPublicIp: false,
    });

    // ----------------------------------------------------------------
    // ALB Target Groups + Listeners
    // ----------------------------------------------------------------
    const fastapiTargetGroup = new elbv2.ApplicationTargetGroup(this, 'FastApiTG', {
      vpc,
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [fastapiService],
      deregistrationDelay: cdk.Duration.seconds(30),
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(10),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    const streamlitTargetGroup = new elbv2.ApplicationTargetGroup(this, 'StreamlitTG', {
      vpc,
      port: 8501,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [streamlitService],
      healthCheck: {
        path: '/_stcore/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(10),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    // HTTP listener — Streamlit on root, FastAPI on /api/*
    const httpListener = alb.addListener('HttpListener', {
      port: 80,
      defaultTargetGroups: [streamlitTargetGroup],
    });

    httpListener.addTargetGroups('FastApiTarget', {
      targetGroups: [fastapiTargetGroup],
      conditions: [elbv2.ListenerCondition.pathPatterns([
        '/health',
        '/docs',
        '/auth',
        '/auth/*',
        '/questions',
      ])],
      priority: 10,
    });

    httpListener.addTargetGroups('FastApiTarget2', {
      targetGroups: [fastapiTargetGroup],
      conditions: [elbv2.ListenerCondition.pathPatterns([
        '/assessments',
        '/assessments/*',
        '/assessments/*/*',
        '/assessments/*/*/*',  
      ])],
      priority: 11,
    });

    httpListener.addTargetGroups('FastApiTarget3', {
      targetGroups: [fastapiTargetGroup],
      conditions: [elbv2.ListenerCondition.pathPatterns([
        '/organisations',
        '/organisations/*',
        '/admin',
        '/admin/*',
      ])],
      priority: 12,
    });
    // ----------------------------------------------------------------
    // CloudFront Distribution
    // ----------------------------------------------------------------
    const distribution = new cloudfront.Distribution(this, 'AiMaturityDistribution', {
      defaultBehavior: {
        origin: new origins.LoadBalancerV2Origin(alb, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
      },
      comment: 'AI Maturity Platform',
    });

    // ----------------------------------------------------------------
    // Outputs
    // ----------------------------------------------------------------
    new cdk.CfnOutput(this, 'CloudFrontUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'CloudFront URL — use this as your live demo link',
    });

    new cdk.CfnOutput(this, 'AlbDnsName', {
      value: alb.loadBalancerDnsName,
      description: 'ALB DNS name',
    });

    new cdk.CfnOutput(this, 'RdsEndpoint', {
      value: dbInstance.instanceEndpoint.hostname,
      description: 'RDS endpoint for migrations',
    });

    new cdk.CfnOutput(this, 'FastApiEcrUri', {
      value: fastapiRepo.repositoryUri,
      description: 'ECR URI for FastAPI image',
    });

    new cdk.CfnOutput(this, 'StreamlitEcrUri', {
      value: streamlitRepo.repositoryUri,
      description: 'ECR URI for Streamlit image',
    });
  }
}