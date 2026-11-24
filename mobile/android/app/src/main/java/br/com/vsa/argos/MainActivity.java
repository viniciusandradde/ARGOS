package br.com.vsa.argos;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(LeitorQrPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
