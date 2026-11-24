package br.com.vsa.argos;

import android.app.Activity;
import android.content.Intent;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.mlkit.common.MlKitException;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning;
import com.google.zxing.client.android.Intents;
import com.journeyapps.barcodescanner.ScanOptions;

@CapacitorPlugin(name = "LeitorQr")
public class LeitorQrPlugin extends Plugin {
    @PluginMethod
    public void escanear(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            GmsBarcodeScannerOptions options = new GmsBarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .enableAutoZoom()
                .build();
            GmsBarcodeScanning.getClient(getActivity(), options).startScan()
                .addOnSuccessListener(barcode -> devolverCodigo(call, barcode.getRawValue()))
                .addOnCanceledListener(call::resolve)
                .addOnFailureListener(error -> {
                    if (error instanceof MlKitException) {
                        int code = ((MlKitException) error).getErrorCode();
                        if (code == MlKitException.CODE_SCANNER_CANCELLED || code == MlKitException.CANCELLED) {
                            call.resolve();
                            return;
                        }
                        if (code == MlKitException.CODE_SCANNER_CAMERA_PERMISSION_NOT_GRANTED) {
                            call.reject("O leitor do Google precisa de acesso à câmera. Você também pode escolher uma foto.");
                            return;
                        }
                        if (code == MlKitException.CODE_SCANNER_TASK_IN_PROGRESS) {
                            call.reject("Uma leitura já está em andamento.");
                            return;
                        }
                    }
                    escanearComLeitorLocal(call);
                });
        });
    }

    private void escanearComLeitorLocal(PluginCall call) {
        Activity activity = getActivity();
        if (activity.isFinishing() || activity.isDestroyed()) {
            call.resolve();
            return;
        }
        // Sideloaded APKs may not have the Google Play scanner module on first use.
        ScanOptions options = new ScanOptions()
            .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setOrientationLocked(false)
            .setBeepEnabled(false)
            .setPrompt("Enquadre o QR Code da nota fiscal");
        startActivityForResult(call, options.createScanIntent(activity), "resultadoLocal");
    }

    @ActivityCallback
    private void resultadoLocal(PluginCall call, ActivityResult result) {
        if (call == null) return;
        Intent data = result.getData();
        if (data != null && data.getBooleanExtra(Intents.Scan.MISSING_CAMERA_PERMISSION, false)) {
            call.reject("Permita o acesso à câmera nas configurações do ARGOS ou escolha uma foto.");
        } else if (result.getResultCode() == Activity.RESULT_OK && data != null) {
            devolverCodigo(call, data.getStringExtra(Intents.Scan.RESULT));
        } else {
            call.resolve();
        }
    }

    private void devolverCodigo(PluginCall call, String valor) {
        if (valor == null || valor.trim().isEmpty()) {
            call.reject("O QR Code veio sem conteúdo. Tente enquadrá-lo novamente.");
            return;
        }
        JSObject resultado = new JSObject();
        resultado.put("valor", valor);
        call.resolve(resultado);
    }
}
