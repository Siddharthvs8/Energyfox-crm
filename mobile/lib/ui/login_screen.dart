import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/auth.dart';
import '../theme.dart';
import 'widgets/common.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();

  bool _showPassword = false;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    // The server is fixed at build time (ApiClient.kProductionBase), so there
    // is nothing to ask for here beyond the username and password.
    final auth = context.read<AuthController>();
    await auth.signIn(
      username: _username.text,
      password: _password.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final media = MediaQuery.of(context);

    return Scaffold(
      backgroundColor: Brand.navy,
      body: Container(
        decoration: const BoxDecoration(gradient: Brand.gradient),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(
                  24, 32, 24, 32 + media.viewInsets.bottom),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _header(),
                    const SizedBox(height: 28),
                    _card(auth),
                    const SizedBox(height: 22),
                    Text(
                      'EnergyFox Consultants Pvt Ltd',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 11.5,
                        letterSpacing: 1.6,
                        fontWeight: FontWeight.w600,
                        color: Colors.white.withValues(alpha: 0.35),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _header() {
    return Column(
      children: [
        Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(26),
            boxShadow: [
              BoxShadow(
                color: Brand.amber.withValues(alpha: 0.22),
                blurRadius: 40,
                spreadRadius: 2,
              ),
            ],
          ),
          child: const BrandMark(size: 86, radius: 26),
        ),
        const SizedBox(height: 20),
        const Text(
          'EnergyFox CRM',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.white,
            fontSize: 26,
            fontWeight: FontWeight.w800,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          "Your team's leads, tasks and deals — in your pocket.",
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 13.5,
            height: 1.4,
            color: Colors.white.withValues(alpha: 0.6),
          ),
        ),
      ],
    );
  }

  Widget _card(AuthController auth) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 22),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Welcome back',
              style: TextStyle(
                color: Colors.white,
                fontSize: 19,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 18),
            if (auth.error != null) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: Brand.danger.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Brand.danger.withValues(alpha: 0.4)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline_rounded,
                        size: 18, color: Color(0xFFFFB3C0)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        auth.error!,
                        style: const TextStyle(
                            color: Color(0xFFFFD6DD), fontSize: 13, height: 1.35),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
            _field(
              controller: _username,
              label: 'Username',
              icon: Icons.person_outline_rounded,
              textInputAction: TextInputAction.next,
              autofillHints: const [AutofillHints.username],
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Enter your username' : null,
            ),
            const SizedBox(height: 14),
            _field(
              controller: _password,
              label: 'Password',
              icon: Icons.lock_outline_rounded,
              obscure: !_showPassword,
              textInputAction: TextInputAction.done,
              autofillHints: const [AutofillHints.password],
              onSubmitted: (_) => _submit(),
              validator: (v) =>
                  (v == null || v.isEmpty) ? 'Enter your password' : null,
              suffix: IconButton(
                onPressed: () => setState(() => _showPassword = !_showPassword),
                icon: Icon(
                  _showPassword
                      ? Icons.visibility_off_outlined
                      : Icons.visibility_outlined,
                  size: 20,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: auth.busy ? null : _submit,
              style: FilledButton.styleFrom(
                backgroundColor: Brand.amber,
                foregroundColor: Brand.navyDeep,
                disabledBackgroundColor: Brand.amber.withValues(alpha: 0.45),
              ),
              child: auth.busy
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.2, color: Brand.navyDeep),
                    )
                  : const Text('Sign in'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    bool obscure = false,
    Widget? suffix,
    String? Function(String?)? validator,
    TextInputAction? textInputAction,
    TextInputType? keyboardType,
    Iterable<String>? autofillHints,
    void Function(String)? onSubmitted,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      validator: validator,
      textInputAction: textInputAction,
      keyboardType: keyboardType,
      autofillHints: autofillHints,
      onFieldSubmitted: onSubmitted,
      style: const TextStyle(color: Colors.white, fontSize: 15),
      cursorColor: Brand.amber,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, size: 20, color: Colors.white.withValues(alpha: 0.5)),
        suffixIcon: suffix,
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.55)),
        floatingLabelStyle: const TextStyle(color: Brand.amber),
        errorStyle: const TextStyle(color: Color(0xFFFFB3C0)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.14)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Brand.amber, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Brand.danger),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Brand.danger, width: 1.5),
        ),
      ),
    );
  }
}
