from aws_cdk import (
    Stack, RemovalPolicy, CfnOutput,
    aws_cognito as cognito,
    aws_iam as iam
)
from constructs import Construct

class TradingAuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # User Pool - RENAMED
        self.user_pool = cognito.UserPool(
            self, "svc-trd-user-pool",  # ← Changed
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # User Pool Client - RENAMED
        self.user_pool_client = cognito.UserPoolClient(
            self, "svc-trd-user-pool-client",  # ← Changed
            user_pool=self.user_pool,
            generate_secret=True,
            auth_flows=cognito.AuthFlow(user_password=True),
        )

        # Identity Pool - RENAMED
        self.identity_pool = cognito.CfnIdentityPool(
            self, "svc-trd-identity-pool",  # ← Changed
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[{
                "clientId": self.user_pool_client.user_pool_client_id,
                "providerName": self.user_pool.user_pool_provider_name
            }]
        )

        # IAM Role for authenticated users - RENAMED
        self.authenticated_role = iam.Role(
            self, "svc-trd-auth-role",  # ← Changed
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                {
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    }
                },
                "sts:AssumeRoleWithWebIdentity"
            )
        )

        # Attach role to identity pool
        cognito.CfnIdentityPoolRoleAttachment(
            self, "svc-trd-identity-pool-attachment",  # ← Changed
            identity_pool_id=self.identity_pool.ref,
            roles={"authenticated": self.authenticated_role.role_arn}
        )

        # Outputs
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(self, "IdentityPoolId", value=self.identity_pool.ref)